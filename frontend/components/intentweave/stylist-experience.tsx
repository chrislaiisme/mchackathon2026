"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Heart,
  Info,
  Mic,
  RefreshCw,
  Send,
  Shirt,
  SlidersHorizontal,
  Square,
  Star,
  ThumbsDown,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import {
  createChatRecommendation,
  createStylistReply,
} from "@/lib/mock/stylist";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import { onboardingService, type OnboardingProfile } from "@/lib/services/onboarding";
import { outfitKeyFromItems, preferenceService } from "@/lib/services/preferences";
import {
  adaptConceptZonesToChatRecommendation,
  adaptToChatRecommendation,
  adaptToClarifyingMessage,
  conceptCellsToRecommendations,
  fetchConceptImage,
  fetchIntentTurn,
  fetchRecommendation,
  StylistApiError,
  type BackendClarifyingQuestion,
} from "@/lib/services/stylist";
import {
  defaultVirtualYouImage,
  virtualYouService,
} from "@/lib/services/virtual-you";
import type {
  ChatMessage,
  ChatRecommendation,
  Conversation,
  FashionRecommendation,
  OutfitRecommendation,
  PreferenceDimensionRatings,
  PreferenceRatingDimension,
  PreferenceSignal,
  UserPreferenceState,
  VirtualYouMeasurements,
  VirtualYouProfile,
  VisualChoice,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const preferenceRatingDimensions: {
  id: PreferenceRatingDimension;
  title: string;
  low: string;
  high: string;
}[] = [
  { id: "visual_impact", title: "吸睛程度", low: "低調簡約", high: "醒目吸睛" },
  { id: "polished_formality", title: "正式程度", low: "輕鬆休閒", high: "俐落正式" },
  { id: "soft_energy", title: "輕盈活動感", low: "挺拔有型", high: "柔軟靈活" },
];

function PreferenceDimensionControl({
  dimension,
  value,
  onChange,
}: {
  dimension: (typeof preferenceRatingDimensions)[number];
  value?: number;
  onChange: (value: number) => void;
}) {
  const [hoveredValue, setHoveredValue] = useState<number>();
  const displayValue = hoveredValue ?? value ?? 0;

  return (
    <div className="space-y-1.5">
      <p className="text-sm text-foreground">{dimension.title}</p>
      <div className="grid grid-cols-[minmax(4.5rem,1fr)_auto_minmax(4.5rem,1fr)] items-center gap-2">
        <span className="text-xs leading-5 text-muted-foreground">{dimension.low}</span>
        <div className="flex items-center gap-0.5" aria-label={dimension.title} onMouseLeave={() => setHoveredValue(undefined)}>
          {[1, 2, 3, 4, 5].map((ratingValue) => {
            const active = ratingValue <= displayValue;
            const selected = value === ratingValue;

            return (
              <button
                key={ratingValue}
                type="button"
                onClick={() => onChange(ratingValue)}
                onFocus={() => setHoveredValue(ratingValue)}
                onBlur={() => setHoveredValue(undefined)}
                onMouseEnter={() => setHoveredValue(ratingValue)}
                className={cn(
                  "flex size-7 cursor-pointer items-center justify-center text-muted-foreground/45 transition hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                  active && "text-primary",
                )}
                aria-label={`${dimension.title} ${ratingValue} 分`}
                aria-pressed={selected}
              >
                <Star className={cn("size-4 transition-colors", active && "fill-current")} />
              </button>
            );
          })}
        </div>
        <span className="text-right text-xs leading-5 text-muted-foreground">{dimension.high}</span>
      </div>
    </div>
  );
}

function ClothingPreferenceRatings({
  itemName,
  ratings,
  onRate,
  compact = false,
}: {
  itemName: string;
  ratings?: PreferenceDimensionRatings;
  onRate: (dimension: PreferenceRatingDimension, value: number) => void;
  compact?: boolean;
}) {
  return (
    <div className={cn("space-y-3 border-t border-border/70 pt-3", compact && "space-y-2.5 pt-3")}>
      <div>
        <p className="text-sm text-foreground">這件單品給你什麼感覺？</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">告訴我們你的直覺，讓推薦越來越懂你。</p>
        {compact && <p className="mt-1 text-xs text-muted-foreground">{itemName}</p>}
      </div>
      <div className={cn("space-y-3", compact && "space-y-2.5")}>
        {preferenceRatingDimensions.map((dimension) => (
          <PreferenceDimensionControl
            key={dimension.id}
            dimension={dimension}
            value={ratings?.[dimension.id]}
            onChange={(value) => onRate(dimension.id, value)}
          />
        ))}
      </div>
    </div>
  );
}

function RecommendationCard({
  item,
  onFeedback,
  onToggleSaved,
  onRate,
  onTryOn,
  feedback,
  saved,
  rating,
  isTryOnActive,
  isTryOnLoading,
}: {
  item: FashionRecommendation;
  onFeedback: (item: FashionRecommendation, value: "dislike") => void;
  onToggleSaved: (item: FashionRecommendation) => void;
  onRate: (itemId: string, dimension: PreferenceRatingDimension, rating: number) => void;
  onTryOn: (item: FashionRecommendation) => void;
  feedback?: "like" | "dislike";
  saved: boolean;
  rating?: PreferenceDimensionRatings;
  isTryOnActive: boolean;
  isTryOnLoading: boolean;
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
              size="sm"
              variant={isTryOnActive ? "default" : "outline"}
              onClick={() => onTryOn(item)}
              disabled={isTryOnLoading}
              aria-pressed={isTryOnActive}
            >
              {isTryOnActive ? <Heart className="size-4 fill-current" /> : <Shirt className="size-4" />}
              <span className={isTryOnActive ? "group-hover/button:hidden" : undefined}>
                {isTryOnActive ? t.virtualYou.onYou : t.virtualYou.tryOn}
              </span>
              {isTryOnActive && <span className="hidden group-hover/button:inline">{t.virtualYou.removeTryOn}</span>}
            </Button>
            <Button
              size="icon-sm"
              variant={saved ? "default" : "outline"}
              aria-label={`Save ${item.name}`}
              onClick={() => onToggleSaved(item)}
            >
              <Bookmark className={`size-4 ${saved ? "fill-current" : ""}`} />
            </Button>
            <Button
              size="icon-sm"
              variant={feedback === "dislike" ? "destructive" : "outline"}
              aria-label={`${t.stylist.dislike} ${item.name}`}
              onClick={() => onFeedback(item, "dislike")}
            >
              <ThumbsDown className="size-4" />
            </Button>
          </div>
        </div>
        <ClothingPreferenceRatings
          itemName={item.name}
          ratings={rating}
          onRate={(dimension, value) => onRate(item.id, dimension, value)}
          compact
        />
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
  onToggleSaved,
  onTryOn,
  onTryOnOutfit,
  onRecommendationNavigate,
  onRecommendationTryMore,
  onRecommendationBackToTopPick,
  onRecommendationRate,
  onRecommendationToggleSaved,
  onRecommendationSaveLook,
  onDesignForMe,
  choicesDisabled,
  feedback,
  preferenceState,
  activeTryOnItemIds,
  recommendationState,
  tryOnState,
  tryOnStatus,
}: {
  message: ChatMessage;
  index: number;
  onChoice: (prompt: string) => void;
  onFeedback: (item: FashionRecommendation, value: "dislike") => void;
  onToggleSaved: (messageId: string, item: FashionRecommendation) => void;
  onTryOn: (item: FashionRecommendation) => void;
  onTryOnOutfit: (outfit: OutfitRecommendation) => void;
  onRecommendationNavigate: (messageId: string, slot: "topOrDress" | "bottom", index: number) => void;
  onRecommendationTryMore: (messageId: string) => void;
  onRecommendationBackToTopPick: (messageId: string) => void;
  onRecommendationRate: (messageId: string, itemId: string, dimension: PreferenceRatingDimension, rating: number) => void;
  onRecommendationToggleSaved: (messageId: string, item: FashionRecommendation) => void;
  onRecommendationSaveLook: (messageId: string) => void;
  onDesignForMe: (messageId: string) => void;
  choicesDisabled: boolean;
  feedback: Record<string, "like" | "dislike">;
  preferenceState: UserPreferenceState;
  activeTryOnItemIds: string[];
  recommendationState?: RecommendationUiState;
  tryOnState: TryOnState;
  tryOnStatus: "idle" | "generating" | "error";
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
            <Button key={choice.id} variant="outline" size="sm" onClick={() => onChoice(choice.prompt)} disabled={choicesDisabled}>
              {choice.label}
            </Button>
          ))}
          <span className="px-2 py-1 text-sm text-muted-foreground">{t.stylist.noneOfThese}</span>
        </div>
      )}

      {message.recommendations && (
        <div className="grid gap-4 md:grid-cols-3">
          {message.recommendations.map((item) => (
            <RecommendationCard
              key={item.id}
              item={item}
              feedback={feedback[item.id]}
              saved={Boolean(preferenceState.savedItems[item.id])}
              rating={preferenceState.itemRatings[item.id]}
              onFeedback={onFeedback}
              onToggleSaved={(nextItem) => onToggleSaved(message.id, nextItem)}
              onRate={(itemId, dimension, rating) => onRecommendationRate(message.id, itemId, dimension, rating)}
              onTryOn={onTryOn}
              isTryOnActive={activeTryOnItemIds.includes(item.id)}
              isTryOnLoading={tryOnStatus === "generating"}
            />
          ))}
        </div>
      )}

      {recommendationState && (
        <ConversationRecommendation
          state={recommendationState}
          onNavigate={(slot, nextIndex) => onRecommendationNavigate(message.id, slot, nextIndex)}
          onTryOn={onTryOn}
          onTryOnOutfit={onTryOnOutfit}
          onFeedback={onFeedback}
          onTryMore={() => onRecommendationTryMore(message.id)}
          onBackToTopPick={() => onRecommendationBackToTopPick(message.id)}
          activeTryOnItemIds={activeTryOnItemIds}
          tryOnState={tryOnState}
          tryOnStatus={tryOnStatus}
          feedback={feedback}
          preferenceState={preferenceState}
          onRate={(itemId, dimension, rating) => onRecommendationRate(message.id, itemId, dimension, rating)}
          onToggleSaved={(item) => onRecommendationToggleSaved(message.id, item)}
          onSaveLook={() => onRecommendationSaveLook(message.id)}
          onDesignForMe={() => onDesignForMe(message.id)}
          designForMeDisabled={choicesDisabled}
        />
      )}
    </section>
  );
}

interface CreateYouApiErrorDetails {
  extractionStatus?: number;
  extractionBody?: string;
  message?: string;
}

type TryOnStatus = "idle" | "generating" | "error";

interface TryOnState {
  topOrDress: FashionRecommendation | null;
  bottom: FashionRecommendation | null;
}

interface TryOnOverlay {
  id: string;
  imageUrl: string;
  slot: "topOrDress" | "bottom";
}

interface StyledMessage {
  title: string;
  summary?: string;
  reason: string;
}

type RecommendationUiState = ChatRecommendation;

interface TranscriptionResponse {
  text?: string;
  error?: string;
  details?: string;
}

class CreateYouError extends Error {
  details?: CreateYouApiErrorDetails;

  constructor(message: string, details?: CreateYouApiErrorDetails) {
    super(message);
    this.name = "CreateYouError";
    this.details = details;
  }
}

function createEmptyPreferenceState(): UserPreferenceState {
  return {
    savedItems: {},
    dislikedItems: {},
    itemRatings: {},
    tryOnFeedback: {},
    recentRecommendationRounds: [],
  };
}

function getCreateYouErrorCode(error: unknown) {
  return error instanceof CreateYouError ? error.message : error instanceof Error ? error.message : "image_processing_failed";
}

function getItemSlot(item: FashionRecommendation): "topOrDress" | "bottom" {
  if (item.itemType === "bottom" || item.id.startsWith("bottom-")) {
    return "bottom";
  }

  return "topOrDress";
}

function isDress(item: FashionRecommendation | null) {
  return item?.itemType === "dress" || Boolean(item?.id.startsWith("dress-"));
}

function createRecommendationUiState(recommendation: ChatRecommendation, locale: Parameters<typeof createChatRecommendation>[0]): RecommendationUiState {
  const fallbackRecommendation = createChatRecommendation(locale);
  const legacyRecommendation = recommendation as Partial<ChatRecommendation> & {
    topOrDressCandidates?: FashionRecommendation[];
    bottomCandidates?: FashionRecommendation[];
    selectedTopOrDressIndex?: number;
    selectedBottomIndex?: number;
  };
  const normalizedRecommendation: ChatRecommendation = recommendation.topPick
    ? recommendation
    : {
        view: "top-pick",
        topPick: fallbackRecommendation.topPick,
        alternatives: {
          topOrDressCandidates: legacyRecommendation.topOrDressCandidates || fallbackRecommendation.alternatives.topOrDressCandidates,
          bottomCandidates: legacyRecommendation.bottomCandidates || fallbackRecommendation.alternatives.bottomCandidates,
          selectedTopOrDressIndex: legacyRecommendation.selectedTopOrDressIndex || 0,
          selectedBottomIndex: legacyRecommendation.selectedBottomIndex || 0,
        },
      };

  return {
    ...normalizedRecommendation,
  };
}

function RecommendationCarousel({
  title,
  items,
  index,
  onNavigate,
  onTryOn,
  onFeedback,
  activeTryOnItemIds,
  tryOnStatus,
  feedback,
  rating,
  onRate,
  saved,
  onToggleSaved,
  disabledReason,
}: {
  title: string;
  items: FashionRecommendation[];
  index: number;
  onNavigate: (nextIndex: number) => void;
  onTryOn: (item: FashionRecommendation) => void;
  onFeedback: (item: FashionRecommendation, value: "dislike") => void;
  activeTryOnItemIds: string[];
  tryOnStatus: TryOnStatus;
  feedback: Record<string, "like" | "dislike">;
  rating?: PreferenceDimensionRatings;
  onRate: (itemId: string, dimension: PreferenceRatingDimension, rating: number) => void;
  saved: boolean;
  onToggleSaved: (item: FashionRecommendation) => void;
  disabledReason?: string;
}) {
  const { t } = useI18n();

  if (items.length === 0) {
    // 這一區沒有候選商品——資料庫那邊連身裙的下身區本來就會故意留空
    // （zones.py 的 is_dress() 規則），生圖那邊理論上兩區都會有六格，但
    // 單一格生成失敗、被 slice_grid.py 的版面檢查擋下時也可能整區變空。
    // 兩種情況都不該讓 `items[index]` 直接炸掉，秀一個空狀態卡片就好。
    return (
      <article className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 border border-dashed border-border bg-card/40 p-6 text-center text-sm text-muted-foreground sm:min-h-[360px] xl:min-h-[400px]">
        <p className="text-xs uppercase tracking-[0.22em]">{title}</p>
        <p>{disabledReason || "No options for this zone."}</p>
      </article>
    );
  }

  const item = items[index];
  const isTryOnActive = activeTryOnItemIds.includes(item.id);

  function move(direction: -1 | 1) {
    onNavigate((index + direction + items.length) % items.length);
  }

  return (
    <article className="flex h-full overflow-hidden border border-border bg-card transition">
      <div className="flex min-w-0 flex-1 flex-col">
        <div
          className="fashion-image relative h-[320px] bg-muted transition duration-500 sm:h-[360px] xl:h-[400px]"
          style={{ backgroundImage: `url(${item.imageUrl})` }}
          aria-label={item.name}
        >
          <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-foreground/35 to-transparent" aria-hidden="true" />
          <div className="absolute left-5 top-5 text-primary-foreground drop-shadow-sm">
            <p className="text-xs uppercase tracking-[0.22em]">{title}</p>
            <p className="mt-2 text-lg tabular-nums">
              {String(index + 1).padStart(2, "0")} / {String(items.length).padStart(2, "0")}
            </p>
          </div>
          <Button
            type="button"
            size="icon-lg"
            variant="outline"
            onClick={() => move(-1)}
            aria-label={`Previous ${title}`}
            className="absolute left-5 top-1/2 -translate-y-1/2 rounded-full border-white/50 bg-card/80 text-foreground shadow-sm backdrop-blur-md hover:bg-card"
          >
            <ChevronLeft className="size-5" />
          </Button>
          <Button
            type="button"
            size="icon-lg"
            variant="outline"
            onClick={() => move(1)}
            aria-label={`Next ${title}`}
            className="absolute right-5 top-1/2 -translate-y-1/2 rounded-full border-white/50 bg-card/80 text-foreground shadow-sm backdrop-blur-md hover:bg-card"
          >
            <ChevronRight className="size-5" />
          </Button>
        </div>
        <div className="flex flex-1 flex-col justify-between gap-5 p-5 sm:p-6">
          <div className="space-y-4">
          <div>
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-serif text-2xl leading-tight text-foreground">{item.name}</h3>
              <span className="mt-1 shrink-0 border-b border-primary/60 pb-1 text-sm text-muted-foreground">
                {item.confidence}% {t.stylist.match}
              </span>
            </div>
            <p className="mt-4 line-clamp-2 text-sm leading-6 text-muted-foreground">{item.explanation}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {item.attributes.slice(0, 3).map((attribute) => (
              <span key={attribute} className="border border-border bg-background/40 px-2.5 py-1 text-xs text-muted-foreground">
                {attribute}
              </span>
            ))}
          </div>
          <ClothingPreferenceRatings
            itemName={item.name}
            ratings={rating}
            onRate={(dimension, value) => onRate(item.id, dimension, value)}
          />
        </div>
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
            <Button
              type="button"
              size="lg"
              variant={isTryOnActive ? "default" : "outline"}
              onClick={() => onTryOn(item)}
              disabled={tryOnStatus === "generating" || Boolean(disabledReason)}
              title={disabledReason}
              aria-pressed={isTryOnActive}
            >
              {isTryOnActive ? <Heart className="size-4 fill-current" /> : <Shirt className="size-4" />}
              {isTryOnActive ? t.virtualYou.onYou : t.virtualYou.tryOn}
            </Button>
            <Button
              type="button"
              size="icon-lg"
              variant={saved ? "default" : "outline"}
              onClick={() => onToggleSaved(item)}
              aria-label={`Save ${item.name}`}
            >
              <Bookmark className={`size-4 ${saved ? "fill-current" : ""}`} />
            </Button>
            <Button
              type="button"
              size="icon-lg"
              variant={feedback[item.id] === "dislike" ? "destructive" : "outline"}
              onClick={() => onFeedback(item, "dislike")}
              aria-label={`${t.stylist.dislike} ${item.name}`}
            >
              <ThumbsDown className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

function CompleteOutfitCard({
  outfit,
  itemRatings,
  saved,
  disliked,
  isTryOnActive,
  isTryOnLoading,
  onTryOn,
  onRate,
  onToggleSaved,
  onDislike,
  onTryMore,
  onDesignForMe,
  designForMeDisabled,
}: {
  outfit: OutfitRecommendation;
  itemRatings: UserPreferenceState["itemRatings"];
  saved: boolean;
  disliked: boolean;
  isTryOnActive: boolean;
  isTryOnLoading: boolean;
  onTryOn: () => void;
  onRate: (itemId: string, dimension: PreferenceRatingDimension, rating: number) => void;
  onToggleSaved: () => void;
  onDislike: () => void;
  onTryMore: () => void;
  onDesignForMe: () => void;
  designForMeDisabled: boolean;
}) {
  const { t } = useI18n();
  const garmentLine = outfit.items.bottom
    ? `${outfit.items.topOrDress.name} + ${outfit.items.bottom.name}`
    : outfit.items.topOrDress.name;
  const hasBottom = Boolean(outfit.items.bottom) && !isDress(outfit.items.topOrDress);
  const imagePanels = [
    {
      id: outfit.items.topOrDress.id,
      label: isDress(outfit.items.topOrDress) ? "Dress" : "Top",
      eyebrow: "Complete Look",
      name: outfit.items.topOrDress.name,
      imageUrl: outfit.items.topOrDress.imageUrl,
    },
    ...(hasBottom && outfit.items.bottom
      ? [
          {
            id: outfit.items.bottom.id,
            label: "Bottom",
            eyebrow: "Stylist's Pick",
            name: outfit.items.bottom.name,
            imageUrl: outfit.items.bottom.imageUrl,
          },
        ]
      : []),
  ];

  return (
    <div className="md:pl-[100px]">
      <article className="overflow-hidden border border-border bg-card">
        <div className={cn("grid border-b border-border", hasBottom ? "sm:grid-cols-2" : "grid-cols-1")}>
          {imagePanels.map((panel) => (
            <div
              key={panel.id}
              className="fashion-image relative h-[320px] bg-muted sm:h-[440px]"
              style={{ backgroundImage: `url(${panel.imageUrl})` }}
              aria-label={panel.name}
            >
              <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-foreground/35 to-transparent" aria-hidden="true" />
              <div className="absolute left-5 top-5 text-primary-foreground drop-shadow-sm">
                <p className="text-xs uppercase tracking-[0.22em]">{panel.eyebrow}</p>
                <p className="mt-2 text-lg">{panel.label}</p>
              </div>
              <div className="absolute bottom-5 left-5 right-5">
                <p className="inline border border-white/45 bg-card/80 px-3 py-2 text-xs text-foreground shadow-sm backdrop-blur-md">
                  {panel.name}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-5 p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-serif text-3xl leading-tight text-foreground">{outfit.name}</h3>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{garmentLine}</p>
            </div>
            <span className="mt-1 shrink-0 border-b border-primary/60 pb-1 text-sm text-muted-foreground">
              {outfit.matchScore}% {t.stylist.match}
            </span>
          </div>

          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{outfit.explanation}</p>

          <div className="flex flex-wrap gap-1.5">
            {outfit.tags.map((tag) => (
              <span key={tag} className="border border-border bg-background/40 px-2.5 py-1 text-xs text-muted-foreground">
                {tag}
              </span>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {[outfit.items.topOrDress, outfit.items.bottom].filter((item): item is FashionRecommendation => Boolean(item)).map((item) => (
              <ClothingPreferenceRatings
                key={item.id}
                itemName={item.name}
                ratings={itemRatings[item.id]}
                onRate={(dimension, value) => onRate(item.id, dimension, value)}
                compact
              />
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="grid min-w-[280px] flex-1 grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
              <Button type="button" size="lg" variant={isTryOnActive ? "default" : "outline"} onClick={onTryOn} disabled={isTryOnLoading}>
                {isTryOnActive ? <Heart className="size-4 fill-current" /> : <Shirt className="size-4" />}
                {isTryOnActive ? t.virtualYou.onYou : t.virtualYou.tryOn}
              </Button>
              <Button type="button" size="icon-lg" variant={saved ? "default" : "outline"} onClick={onToggleSaved} aria-label={`Save ${outfit.name}`}>
                <Bookmark className={`size-4 ${saved ? "fill-current" : ""}`} />
              </Button>
              <Button type="button" size="icon-lg" variant={disliked ? "destructive" : "outline"} onClick={onDislike} aria-label={`Dislike ${outfit.name}`}>
                <ThumbsDown className="size-4" />
              </Button>
            </div>
            <div className="flex gap-4">
              <button
                type="button"
                onClick={onDesignForMe}
                disabled={designForMeDisabled}
                className="border-b border-border pb-1 text-sm text-muted-foreground hover:border-primary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {designForMeDisabled ? t.stylist.generating : "Design for Me"}
              </button>
              <button type="button" onClick={onTryMore} className="border-b border-primary pb-1 text-sm text-foreground">
                Try More →
              </button>
            </div>
          </div>
        </div>
      </article>
    </div>
  );
}

function ConversationRecommendation({
  state,
  onNavigate,
  onTryOn,
  onTryOnOutfit,
  onFeedback,
  onTryMore,
  onBackToTopPick,
  activeTryOnItemIds,
  tryOnState,
  tryOnStatus,
  feedback,
  preferenceState,
  onRate,
  onToggleSaved,
  onSaveLook,
  onDesignForMe,
  designForMeDisabled,
}: {
  state: RecommendationUiState;
  onNavigate: (slot: "topOrDress" | "bottom", index: number) => void;
  onTryOn: (item: FashionRecommendation) => void;
  onTryOnOutfit: (outfit: OutfitRecommendation) => void;
  onFeedback: (item: FashionRecommendation, value: "dislike") => void;
  onTryMore: () => void;
  onBackToTopPick: () => void;
  activeTryOnItemIds: string[];
  tryOnState: TryOnState;
  tryOnStatus: TryOnStatus;
  feedback: Record<string, "like" | "dislike">;
  preferenceState: UserPreferenceState;
  onRate: (itemId: string, dimension: PreferenceRatingDimension, rating: number) => void;
  onToggleSaved: (item: FashionRecommendation) => void;
  onSaveLook: () => void;
  onDesignForMe: () => void;
  designForMeDisabled: boolean;
}) {
  const dressActive = isDress(tryOnState.topOrDress);
  const topPick = state.topPick;

  if (!topPick?.items?.topOrDress) {
    return null;
  }

  const topPickItemIds = [
    topPick.items.topOrDress.id,
    topPick.items.bottom?.id,
  ].filter((itemId): itemId is string => Boolean(itemId));
  const isTopPickTryOnActive = topPickItemIds.length > 0 && topPickItemIds.every((itemId) => activeTryOnItemIds.includes(itemId));

  if (state.view === "top-pick") {
    return (
      <CompleteOutfitCard
        outfit={topPick}
        itemRatings={preferenceState.itemRatings}
        saved={topPickItemIds.length > 0 && topPickItemIds.every((itemId) => Boolean(preferenceState.savedItems[itemId]))}
        disliked={feedback[topPick.id] === "dislike" || topPickItemIds.some((itemId) => feedback[itemId] === "dislike")}
        isTryOnActive={isTopPickTryOnActive}
        isTryOnLoading={tryOnStatus === "generating"}
        onTryOn={() => onTryOnOutfit(topPick)}
        onRate={onRate}
        onToggleSaved={onSaveLook}
        onDislike={() => onFeedback(topPick.items.topOrDress, "dislike")}
        onTryMore={onTryMore}
        onDesignForMe={onDesignForMe}
        designForMeDisabled={designForMeDisabled}
      />
    );
  }

  return (
    <div className="space-y-4 md:pl-[100px]">
      <button type="button" onClick={onBackToTopPick} className="border-b border-primary pb-1 text-sm text-foreground">
        ← Back to Stylist&apos;s Pick
      </button>
      <div className="grid items-stretch gap-5 xl:grid-cols-2">
        <RecommendationCarousel
          title="TOP / DRESS"
          items={state.alternatives.topOrDressCandidates}
          index={state.alternatives.selectedTopOrDressIndex}
          onNavigate={(index) => onNavigate("topOrDress", index)}
          onTryOn={onTryOn}
          onFeedback={onFeedback}
          activeTryOnItemIds={activeTryOnItemIds}
          tryOnStatus={tryOnStatus}
          feedback={feedback}
          rating={
            preferenceState.itemRatings[
              state.alternatives.topOrDressCandidates[state.alternatives.selectedTopOrDressIndex]?.id ?? ""
            ]
          }
          onRate={onRate}
          saved={Boolean(
            preferenceState.savedItems[
              state.alternatives.topOrDressCandidates[state.alternatives.selectedTopOrDressIndex]?.id ?? ""
            ],
          )}
          onToggleSaved={onToggleSaved}
        />
        <RecommendationCarousel
          title="BOTTOM"
          items={state.alternatives.bottomCandidates}
          index={state.alternatives.selectedBottomIndex}
          onNavigate={(index) => onNavigate("bottom", index)}
          onTryOn={onTryOn}
          onFeedback={onFeedback}
          activeTryOnItemIds={activeTryOnItemIds}
          tryOnStatus={tryOnStatus}
          feedback={feedback}
          rating={
            preferenceState.itemRatings[
              state.alternatives.bottomCandidates[state.alternatives.selectedBottomIndex]?.id ?? ""
            ]
          }
          onRate={onRate}
          saved={Boolean(
            preferenceState.savedItems[
              state.alternatives.bottomCandidates[state.alternatives.selectedBottomIndex]?.id ?? ""
            ],
          )}
          onToggleSaved={onToggleSaved}
          disabledReason={dressActive ? "A dress is active as the complete outfit." : undefined}
        />
      </div>
    </div>
  );
}

async function removeBackground(originalUserImage: File) {
  console.log("[CreateYou] Starting segmentation/background removal");
  const { extractedPersonImage: personMask } = await virtualYouService.extractPerson(originalUserImage).catch((error) => {
    console.error("[CreateYou] Backend extraction failed", error);
    const details =
      error instanceof Error && "details" in error && typeof error.details === "object"
        ? (error.details as CreateYouApiErrorDetails)
        : undefined;

    throw new CreateYouError(error instanceof Error ? error.message : "background_removal_failed", details);
  });

  console.log("[CreateYou] Segmentation result:", {
    type: personMask.type,
    size: personMask.size,
  });

  return personMask;
}

async function detectPerson(originalUserImage: File) {
  console.log("[CreateYou] Person detection started");
  const personMask = await removeBackground(originalUserImage);
  console.log("[CreateYou] Person detection result:", {
    maskType: personMask.type,
    maskSize: personMask.size,
  });
  return personMask;
}

async function getPersonBoundingBox(extractedPersonImage: Blob) {
  console.log("[CreateYou] Calculating person bounding box");
  const imageBitmap = await createImageBitmap(extractedPersonImage);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { willReadFrequently: true });

  canvas.width = imageBitmap.width;
  canvas.height = imageBitmap.height;

  if (!context) {
    imageBitmap.close();
    throw new Error("canvas_unavailable");
  }

  context.drawImage(imageBitmap, 0, 0);
  imageBitmap.close();

  const { data, width, height } = context.getImageData(0, 0, canvas.width, canvas.height);
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = data[(y * width + x) * 4 + 3];

      if (alpha > 12) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  }

  if (maxX < minX || maxY < minY) {
    console.error("[CreateYou] No non-transparent pixels found in extracted image");
    throw new CreateYouError("no_person_detected");
  }

  const padding = Math.max(12, Math.round(Math.max(maxX - minX, maxY - minY) * 0.035));
  const x = Math.max(0, minX - padding);
  const y = Math.max(0, minY - padding);
  const right = Math.min(width, maxX + padding + 1);
  const bottom = Math.min(height, maxY + padding + 1);

  const personBoundingBox = {
    x,
    y,
    width: right - x,
    height: bottom - y,
  };

  console.log("[CreateYou] Person bounding box:", personBoundingBox);
  return personBoundingBox;
}

async function normalizePersonImage(extractedPersonImage: Blob) {
  console.log("[CreateYou] Normalizing extracted person image");
  const imageBitmap = await createImageBitmap(extractedPersonImage);
  const personBoundingBox = await getPersonBoundingBox(extractedPersonImage);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");

  canvas.width = personBoundingBox.width;
  canvas.height = personBoundingBox.height;

  if (!context) {
    imageBitmap.close();
    throw new Error("canvas_unavailable");
  }

  context.drawImage(
    imageBitmap,
    personBoundingBox.x,
    personBoundingBox.y,
    personBoundingBox.width,
    personBoundingBox.height,
    0,
    0,
    personBoundingBox.width,
    personBoundingBox.height,
  );
  imageBitmap.close();

  const croppedPersonImage = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("crop_failed"))), "image/png");
  });

  console.log("[CreateYou] Cropped extracted person image:", {
    type: croppedPersonImage.type,
    size: croppedPersonImage.size,
    width: canvas.width,
    height: canvas.height,
  });

  return {
    extractedPersonImage: croppedPersonImage,
    personBoundingBox,
  };
}

async function uploadUserPhoto(originalUserImage: File) {
  console.log("[CreateYou] Starting upload pipeline", {
    name: originalUserImage.name,
    type: originalUserImage.type,
    size: originalUserImage.size,
  });
  const personMask = await detectPerson(originalUserImage);
  const { extractedPersonImage, personBoundingBox } = await normalizePersonImage(personMask);

  console.log("[CreateYou] Upload pipeline complete", {
    originalUserImageSize: originalUserImage.size,
    personMaskSize: personMask.size,
    extractedPersonImageSize: extractedPersonImage.size,
    personBoundingBox,
  });

  return {
    originalUserImage,
    personMask,
    extractedPersonImage,
    personBoundingBox,
  };
}

function VirtualYouFigure({
  baseImage,
  displayImage,
  tryOnOverlays,
  isTryingOn,
  loadingLabel,
}: {
  baseImage: string;
  displayImage: string;
  tryOnOverlays: TryOnOverlay[];
  isTryingOn: boolean;
  loadingLabel: string;
}) {
  return (
    <div className="relative min-h-[320px] overflow-visible">
      <div className="absolute bottom-6 left-1/2 h-[70%] w-[88%] -translate-x-1/2 rounded-[999px] bg-[radial-gradient(ellipse_at_center,rgba(116,55,216,0.14),rgba(238,232,248,0.08)_42%,transparent_72%)]" />
      <div
        className="relative z-10 mx-auto h-[330px] max-h-[42vh] w-full bg-contain bg-bottom bg-no-repeat"
        style={{ backgroundImage: `url(${displayImage || baseImage})` }}
      >
        {tryOnOverlays.map((overlay) => (
          <div
            key={overlay.id}
            className={`pointer-events-none absolute left-1/2 -translate-x-1/2 bg-contain bg-center bg-no-repeat opacity-60 mix-blend-multiply transition duration-500 ${
              overlay.slot === "bottom" ? "top-[48%] h-[34%] w-[54%]" : "top-[23%] h-[42%] w-[58%]"
            }`}
            style={{ backgroundImage: `url(${overlay.imageUrl})` }}
            aria-hidden="true"
          />
        ))}
      </div>
      {isTryingOn && (
        <div className="absolute inset-x-0 top-1/2 z-20 -translate-y-1/2 text-center text-sm leading-6 text-muted-foreground">
          {loadingLabel}
        </div>
      )}
    </div>
  );
}

function TryOnFeedbackControls({
  selected,
  onSelect,
}: {
  selected?: "like" | "dislike";
  onSelect: (feedback: "like" | "dislike") => void;
}) {
  const { t } = useI18n();

  return (
    <div className="space-y-3">
      <p className="text-sm leading-6 text-muted-foreground">{t.virtualYou.tryOnFeedbackPrompt}</p>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={selected === "dislike" ? "destructive" : "outline"}
          onClick={() => onSelect("dislike")}
        >
          <ThumbsDown className="size-4" />
          {t.virtualYou.notForMe}
        </Button>
        <Button
          type="button"
          size="sm"
          variant={selected === "like" ? "default" : "outline"}
          onClick={() => onSelect("like")}
        >
          <Heart className="size-4" />
          {t.virtualYou.loveIt}
        </Button>
      </div>
    </div>
  );
}

function CreateYouSection({
  profile,
  isProcessing,
  error,
  onUpload,
  activeTryOnImage,
  activeTryOnOverlays,
  tryOnStatus,
  tryOnError,
  activeTryOnFeedback,
  onTryOnFeedback,
  canShowTryOnFeedback,
  styledMessage,
}: {
  profile: VirtualYouProfile | null;
  isProcessing: boolean;
  error: string;
  onUpload: (file: File) => void;
  activeTryOnImage: string | null;
  activeTryOnOverlays: TryOnOverlay[];
  tryOnStatus: "idle" | "generating" | "error";
  tryOnError: string;
  activeTryOnFeedback?: "like" | "dislike";
  onTryOnFeedback: (feedback: "like" | "dislike") => void;
  canShowTryOnFeedback: boolean;
  styledMessage: StyledMessage | null;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const baseVirtualYouImage = profile?.modelImageUrl || defaultVirtualYouImage;
  const displayImage = activeTryOnImage ?? baseVirtualYouImage;

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (file) {
      console.log("[CreateYou] File selected", {
        name: file.name,
        type: file.type,
        size: file.size,
      });
      onUpload(file);
    }

    event.target.value = "";
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{t.virtualYou.createYou}</p>
          <Info className="size-3.5 text-muted-foreground" aria-hidden="true" />
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => inputRef.current?.click()} disabled={isProcessing}>
          <Upload className="size-3.5" />
          {t.virtualYou.uploadPhoto}
        </Button>
      </div>
      <input ref={inputRef} type="file" accept="image/*" onChange={handleChange} className="hidden" />
      {isProcessing ? (
        <div className="relative min-h-[320px] overflow-visible">
          <div className="absolute bottom-6 left-1/2 h-[70%] w-[88%] -translate-x-1/2 rounded-[999px] bg-[radial-gradient(ellipse_at_center,rgba(116,55,216,0.14),rgba(238,232,248,0.08)_42%,transparent_72%)]" />
          <div className="relative z-10 flex h-[330px] max-h-[42vh] items-center justify-center text-center text-sm leading-6 text-muted-foreground">
            {t.virtualYou.creatingYou}
          </div>
        </div>
      ) : profile?.hasExtractedPerson || activeTryOnImage || tryOnStatus === "generating" ? (
        <VirtualYouFigure
          baseImage={baseVirtualYouImage}
          displayImage={displayImage}
          tryOnOverlays={activeTryOnOverlays}
          isTryingOn={tryOnStatus === "generating"}
          loadingLabel={t.virtualYou.tryingItOn}
        />
      ) : (
        <div className="relative min-h-[320px] overflow-visible">
          <div className="absolute bottom-6 left-1/2 h-[70%] w-[88%] -translate-x-1/2 rounded-[999px] bg-[radial-gradient(ellipse_at_center,rgba(116,55,216,0.14),rgba(238,232,248,0.08)_42%,transparent_72%)]" />
        </div>
      )}
      {error && <p className="text-sm leading-6 text-destructive">{error}</p>}
      {tryOnError && <p className="text-sm leading-6 text-destructive">{tryOnError}</p>}
      {styledMessage && tryOnStatus !== "generating" && (
        <div className="border-l border-primary bg-accent/40 px-4 py-3">
          <p className="text-sm font-medium text-foreground">{styledMessage.title}</p>
          {styledMessage.summary && <p className="mt-1 text-sm text-primary">{styledMessage.summary}</p>}
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{styledMessage.reason}</p>
        </div>
      )}
      {activeTryOnImage && canShowTryOnFeedback && tryOnStatus !== "generating" && (
        <TryOnFeedbackControls selected={activeTryOnFeedback} onSelect={onTryOnFeedback} />
      )}
    </section>
  );
}

function StylePanel({
  signals,
  feedbackCount,
  styleProfile,
  virtualYou,
  createYouProcessing,
  createYouError,
  onCreateYouUpload,
  activeTryOnImage,
  activeTryOnOverlays,
  tryOnStatus,
  tryOnError,
  activeTryOnFeedback,
  onTryOnFeedback,
  canShowTryOnFeedback,
  styledMessage,
}: {
  signals: PreferenceSignal[];
  feedbackCount: number;
  styleProfile: OnboardingProfile | null;
  virtualYou: VirtualYouProfile | null;
  createYouProcessing: boolean;
  createYouError: string;
  onCreateYouUpload: (file: File) => void;
  activeTryOnImage: string | null;
  activeTryOnOverlays: TryOnOverlay[];
  tryOnStatus: "idle" | "generating" | "error";
  tryOnError: string;
  activeTryOnFeedback?: "like" | "dislike";
  onTryOnFeedback: (feedback: "like" | "dislike") => void;
  canShowTryOnFeedback: boolean;
  styledMessage: StyledMessage | null;
}) {
  const { t } = useI18n();
  const topSignals = styleProfile?.styles.length
    ? styleProfile.styles.slice(0, 4).map((style) => ({ label: style }))
    : signals.filter((signal) => signal.direction !== "down").slice(0, 4);
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
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <Link href="/profile" className="inline-flex border-b border-primary pb-1 text-sm font-medium text-foreground">
          {t.stylist.viewProfile}
        </Link>
        <Link href="/dressing-room" className="inline-flex border-b border-primary pb-1 text-sm font-medium text-foreground">
          {t.nav.dressingRoom}
        </Link>
      </div>
      <CreateYouSection
        profile={virtualYou}
        isProcessing={createYouProcessing}
        error={createYouError}
        onUpload={onCreateYouUpload}
        activeTryOnImage={activeTryOnImage}
        activeTryOnOverlays={activeTryOnOverlays}
        tryOnStatus={tryOnStatus}
        tryOnError={tryOnError}
        activeTryOnFeedback={activeTryOnFeedback}
        onTryOnFeedback={onTryOnFeedback}
        canShowTryOnFeedback={canShowTryOnFeedback}
        styledMessage={styledMessage}
      />
    </aside>
  );
}

function VirtualYouModal({
  open,
  onClose,
  onSave,
  onUseDefault,
  initialProfile,
  storageError,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (photo: File | null, measurements: VirtualYouMeasurements) => Promise<void>;
  onUseDefault: () => Promise<void>;
  initialProfile: VirtualYouProfile | null;
  storageError: string;
}) {
  const { t } = useI18n();
  const [previewUrl, setPreviewUrl] = useState(initialProfile?.modelImageUrl || "");
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null);
  const [measurements, setMeasurements] = useState<VirtualYouMeasurements>(initialProfile?.measurements || {});
  const [isSaving, setIsSaving] = useState(false);
  const localPreviewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (localPreviewUrlRef.current) {
        URL.revokeObjectURL(localPreviewUrlRef.current);
      }
    };
  }, []);

  if (!open) {
    return null;
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    if (localPreviewUrlRef.current) {
      URL.revokeObjectURL(localPreviewUrlRef.current);
    }

    const nextPreviewUrl = URL.createObjectURL(file);
    localPreviewUrlRef.current = nextPreviewUrl;
    setSelectedPhoto(file);
    setPreviewUrl(nextPreviewUrl);
  }

  function updateMeasurement(key: keyof VirtualYouMeasurements, value: string) {
    setMeasurements((current) => ({ ...current, [key]: value }));
  }

  async function handleSave() {
    setIsSaving(true);

    try {
      await onSave(selectedPhoto, measurements);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleUseDefault() {
    setIsSaving(true);

    try {
      await onUseDefault();
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto border border-border bg-card">
        <div className="flex items-start justify-between gap-6 border-b border-border p-6">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{t.virtualYou.title}</p>
            <h2 className="mt-2 font-serif text-4xl leading-tight">{t.virtualYou.createTitle}</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{t.virtualYou.createDescription}</p>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t.virtualYou.close}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="grid gap-6 p-6 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            <label className="block text-sm font-medium">{t.virtualYou.upload}</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleUpload}
              className="mt-3 block w-full text-sm text-muted-foreground file:mr-4 file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-sm"
            />
            <div
              className="fashion-image mt-4 aspect-[3/5] border border-border bg-muted"
              style={{ backgroundImage: `url(${previewUrl || defaultVirtualYouImage})` }}
            />
            {storageError && <p className="mt-3 text-sm leading-6 text-destructive">{storageError}</p>}
          </div>

          <div className="space-y-5">
            <div>
              <h3 className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
                {t.virtualYou.bodyDetails} · {t.virtualYou.optional}
              </h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{t.virtualYou.helper}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["heightCm", t.virtualYou.height, "cm"],
                ["weightKg", t.virtualYou.weight, "kg"],
                ["waistCm", t.virtualYou.waist, "cm"],
                ["hipsCm", t.virtualYou.hips, "cm"],
                ["chestBustCm", t.virtualYou.chestBust, "cm"],
              ].map(([key, label, unit]) => (
                <label key={key} className="block text-sm">
                  <span className="text-muted-foreground">
                    {label} ({unit})
                  </span>
                  <input
                    value={measurements[key as keyof VirtualYouMeasurements] || ""}
                    onChange={(event) => updateMeasurement(key as keyof VirtualYouMeasurements, event.target.value)}
                    inputMode="numeric"
                    className="mt-2 h-10 w-full border border-input bg-background px-3 outline-none focus:border-primary"
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={handleSave} disabled={isSaving}>
                {isSaving ? t.virtualYou.saving : t.virtualYou.save}
              </Button>
              <Button variant="outline" onClick={handleUseDefault} disabled={isSaving}>
                {t.virtualYou.useDefault}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function StylistExperience() {
  const router = useRouter();
  const { locale, t } = useI18n();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  // 2026-09-19 新增：同一輪 ENGINE01 一次回傳多題澄清問題時（例如「一套商業套裝」
  // 一次缺 colors／material／season 好幾個核心欄位），本地依序秀出剩下的題目、
  // 答案先收集在這裡，全部答完才真的打一次 /intent——見 sendPrompt() 跟
  // lib/services/stylist.ts 的 adaptToClarifyingMessage() 註解，兩邊要一起看。
  const [pendingClarifyingQueue, setPendingClarifyingQueue] = useState<BackendClarifyingQuestion[]>([]);
  const [pendingClarifyingAnswers, setPendingClarifyingAnswers] = useState<string[]>([]);
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [voiceElapsedSeconds, setVoiceElapsedSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const [virtualYou, setVirtualYou] = useState<VirtualYouProfile | null>(null);
  const [styleProfile, setStyleProfile] = useState<OnboardingProfile | null>(null);
  const [virtualYouModalOpen, setVirtualYouModalOpen] = useState(false);
  const [virtualYouStorageError, setVirtualYouStorageError] = useState("");
  const [createYouProcessing, setCreateYouProcessing] = useState(false);
  const [createYouError, setCreateYouError] = useState("");
  const [tryOnState, setTryOnState] = useState<TryOnState>({ topOrDress: null, bottom: null });
  const [activeTryOnImage, setActiveTryOnImage] = useState<string | null>(null);
  const [tryOnStatus, setTryOnStatus] = useState<TryOnStatus>("idle");
  const [tryOnError, setTryOnError] = useState("");
  const [preferenceState, setPreferenceState] = useState<UserPreferenceState>(createEmptyPreferenceState);
  const [recommendationStateByMessageId, setRecommendationStateByMessageId] = useState<Record<string, RecommendationUiState>>({});
  const [styledMessage, setStyledMessage] = useState<StyledMessage | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<number | null>(null);
  const shouldFollowRef = useRef(true);
  const virtualYouObjectUrlRef = useRef<string | null>(null);
  const tryOnObjectUrlRef = useRef<string | null>(null);

  const activeConversation = conversations.find((conversation) => conversation.id === activeId);
  const activeTryOnItems = useMemo(
    () => [tryOnState.topOrDress, isDress(tryOnState.topOrDress) ? null : tryOnState.bottom].filter(Boolean) as FashionRecommendation[],
    [tryOnState],
  );
  const activeTryOnItemIds = useMemo(() => activeTryOnItems.map((item) => item.id), [activeTryOnItems]);
  const activeTryOnOverlays = useMemo<TryOnOverlay[]>(() => [], []);
  const canShowTryOnFeedback = Boolean(tryOnState.topOrDress && (isDress(tryOnState.topOrDress) || tryOnState.bottom));

  const replaceVirtualYou = useCallback((nextProfile: VirtualYouProfile | null) => {
    const previousObjectUrl = virtualYouObjectUrlRef.current;
    const nextObjectUrl = nextProfile?.modelImageUrl.startsWith("blob:") ? nextProfile.modelImageUrl : null;

    if (previousObjectUrl && previousObjectUrl !== nextObjectUrl) {
      URL.revokeObjectURL(previousObjectUrl);
    }

    virtualYouObjectUrlRef.current = nextObjectUrl;
    setVirtualYou(nextProfile);
    setVirtualYouStorageError(nextProfile?.storageError ? t.virtualYou.loadError : "");
  }, [t.virtualYou.loadError]);

  const replaceActiveTryOnImage = useCallback((nextImageUrl: string | null) => {
    const previousObjectUrl = tryOnObjectUrlRef.current;
    const nextObjectUrl = nextImageUrl?.startsWith("blob:") ? nextImageUrl : null;

    if (previousObjectUrl && previousObjectUrl !== nextObjectUrl) {
      URL.revokeObjectURL(previousObjectUrl);
    }

    tryOnObjectUrlRef.current = nextObjectUrl;
    setActiveTryOnImage(nextImageUrl);
  }, []);

  const refreshConversations = useCallback(async () => {
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

    if (currentId && nextActiveId && currentId !== nextActiveId) {
      // 真的切換到別的對話了（不是「同一個對話又觸發了一次 refresh」，例如
      // virtual-you／onboarding 變更也會走到這裡）——把「還沒問完的一批
      // clarifying questions」佇列清掉，不然切過去之後點選項，答案會被誤當成
      // 回答上一個對話裡那批還沒問完的題目（pendingClarifyingQueue 是跨對話
      // 共用的 component state，不是存在個別 Conversation 物件裡）。
      setPendingClarifyingQueue([]);
      setPendingClarifyingAnswers([]);
    }

    setConversations(list);
    setActiveId(nextActiveId);
    setStyleProfile(onboardingService.getProfile());
    setPreferenceState(preferenceService.get(user.id));
    replaceVirtualYou(await virtualYouService.get(user.id));
  }, [replaceVirtualYou, router]);

  useEffect(() => {
    queueMicrotask(() => {
      void refreshConversations();
    });

    function handleChange() {
      void refreshConversations();
    }

    window.addEventListener("intentweave-conversations-change", handleChange);
    window.addEventListener("intentweave-auth-change", handleChange);
    window.addEventListener("intentweave-virtual-you-change", handleChange);
    window.addEventListener("intentweave-onboarding-change", handleChange);
    window.addEventListener(preferenceService.changeEvent, handleChange);

    return () => {
      window.removeEventListener("intentweave-conversations-change", handleChange);
      window.removeEventListener("intentweave-auth-change", handleChange);
      window.removeEventListener("intentweave-virtual-you-change", handleChange);
      window.removeEventListener("intentweave-onboarding-change", handleChange);
      window.removeEventListener(preferenceService.changeEvent, handleChange);

      if (virtualYouObjectUrlRef.current) {
        URL.revokeObjectURL(virtualYouObjectUrlRef.current);
      }

      if (tryOnObjectUrlRef.current) {
        URL.revokeObjectURL(tryOnObjectUrlRef.current);
      }
    };
  }, [refreshConversations]);

  useEffect(() => {
    if (shouldFollowRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [activeConversation?.messages.length, isGenerating, activeId]);

  useEffect(() => {
    if (!activeConversation) {
      return;
    }

    queueMicrotask(() => {
      setRecommendationStateByMessageId((current) => {
        let changed = false;
        const next = { ...current };
        const user = authService.getSession();

        activeConversation.messages.forEach((message) => {
          if (message.role !== "assistant" || next[message.id]) {
            return;
          }

          if (message.recommendation) {
            next[message.id] = createRecommendationUiState(message.recommendation, locale);
            if (user) {
              preferenceService.registerRecommendationRound(user.id, message.id);
            }
            changed = true;
            return;
          }

          if (message.recommendations?.length) {
            next[message.id] = createRecommendationUiState(createChatRecommendation(locale), locale);
            if (user) {
              preferenceService.registerRecommendationRound(user.id, message.id);
            }
            changed = true;
          }
        });

        return changed ? next : current;
      });
    });
  }, [activeConversation, locale]);

  useEffect(() => {
    return () => {
      stopVoiceTimer();
      if (mediaRecorderRef.current) {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.onerror = null;

        if (mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop();
        }
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  function stopVoiceTimer() {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
  }

  function formatVoiceTime(seconds: number) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  }

  function getSupportedAudioMimeType() {
    if (!("MediaRecorder" in window)) {
      return "";
    }

    return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((type) =>
      MediaRecorder.isTypeSupported(type),
    );
  }

  function appendTranscription(text: string) {
    const trimmed = text.trim();

    if (!trimmed) {
      return;
    }

    setInput((current) => (current.trim() ? `${current.trimEnd()} ${trimmed}` : trimmed));
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function transcribeAudio(audio: Blob) {
    setVoiceState("transcribing");
    setVoiceError("");

    try {
      console.log("[Voice] Sending audio for transcription", {
        type: audio.type || "(empty)",
        size: audio.size,
      });

      const formData = new FormData();
      const extension = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
      formData.append("audio", audio, `intentweave-voice.${extension}`);

      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
      });
      const result = (await response.json().catch(() => null)) as TranscriptionResponse | null;

      if (!response.ok || !result?.text) {
        console.error("[Voice] Transcription failed", {
          status: response.status,
          error: result?.error,
          details: result?.details,
        });

        if (result?.error === "whisper_unavailable") {
          setVoiceError(t.stylist.voiceConfigError);
        } else if (
          result?.error === "invalid_audio" ||
          result?.error === "unsupported_audio" ||
          result?.error === "transcription_empty"
        ) {
          setVoiceError(t.stylist.voiceInvalidAudioError);
        } else {
          setVoiceError(t.stylist.voiceTranscriptionError);
        }

        return;
      }

      console.log("[Voice] Transcription succeeded", {
        textLength: result.text.length,
      });
      appendTranscription(result.text);
    } catch (error) {
      console.error("[Voice] Transcription request error", error);
      setVoiceError(t.stylist.voiceNetworkError);
    } finally {
      setVoiceState("idle");
    }
  }

  async function startVoiceRecording() {
    if (voiceState !== "idle") {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !("MediaRecorder" in window)) {
      setVoiceError(t.stylist.voiceUnavailable);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getSupportedAudioMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      setVoiceError("");
      setVoiceElapsedSeconds(0);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        setVoiceError(t.stylist.voiceRecordingError);
        stopVoiceTimer();
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaStreamRef.current = null;
        audioChunksRef.current = [];
        setVoiceState("idle");
      };
      recorder.onstop = () => {
        stopVoiceTimer();
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaStreamRef.current = null;

        const audio = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];

        if (audio.size === 0) {
          setVoiceState("idle");
          setVoiceError(t.stylist.voiceRecordingError);
          return;
        }

        void transcribeAudio(audio);
      };

      recorder.start();
      setVoiceState("recording");
      recordingTimerRef.current = window.setInterval(() => {
        setVoiceElapsedSeconds((seconds) => seconds + 1);
      }, 1000);
    } catch (error) {
      const name = error instanceof DOMException ? error.name : "";
      setVoiceError(name === "NotAllowedError" || name === "SecurityError" ? t.stylist.voicePermissionError : t.stylist.voiceRecordingError);
      setVoiceState("idle");
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }

  function stopVoiceRecording() {
    if (voiceState !== "recording") {
      return;
    }

    const recorder = mediaRecorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      stopVoiceTimer();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
      setVoiceState("idle");
    }
  }

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

  // 真的打 ENGINE01 /intent（→有澄清問題就組選擇題；沒有就接著 /recommend
  // 組 Top Pick＋Try More）。`messageForBackend` 是實際要送給後端的一句話——
  // 一般情況下就是使用者這輪打的字／點的選項；但如果這輪是在回答同一個
  // clarifying-question 批次裡的最後一題，`sendPrompt()`（下面）會先把
  // 這一批已經收集到的所有答案合併成一句話，才呼叫這支函式，所以這裡
  // 不能假設 `messageForBackend` 一定等於使用者剛剛打的原始文字。
  // `baseConversation` 是已經包含這一輪使用者訊息泡泡的對話物件（由呼叫端
  // 決定要不要、以及怎麼組出使用者泡泡——見 sendPrompt()），這支函式只管
  // 呼叫後端、把回應接到後面。
  async function runIntentTurn(messageForBackend: string, baseConversation: Conversation) {
    let nextConversation = baseConversation;
    persistConversation(nextConversation);
    setInput("");
    setIsGenerating(true);

    // token 理論上一定有（createNewSession 已經檔過未登入導去 /login），沒有就退回
    // 舊的 mock 回覆，不讓對話卡死。
    const token = authService.getSessionToken();

    if (!token) {
      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      nextConversation = conversationService.appendMessage(latest, createStylistReply(messageForBackend, locale));
      persistConversation(nextConversation);
      setIsGenerating(false);
      return;
    }

    try {
      const intentResult = await fetchIntentTurn(nextConversation.engineSessionId, messageForBackend, token);

      let assistantMessage: ChatMessage;
      if (intentResult.clarifying_questions.length > 0) {
        // 2026-09-19 修正：這裡以前把整批 clarifying_questions 丟給
        // adaptToClarifyingMessage()，但它只轉第一題、其餘題目直接消失——
        // 而後端 gating.py 早就把「這次保留的每一題」都記成已經問過
        // （不是只記第一題），造成那些被丟掉的題目對應的核心欄位永遠不會
        // 再被問、也沒被使用者真的回答過。現在改成只顯示第一題，其餘的存進
        // pendingClarifyingQueue，交給 sendPrompt() 依序秀出來、答完才送出
        // 下一次 /intent（見該函式與 lib/services/stylist.ts 的註解）。
        assistantMessage = adaptToClarifyingMessage(intentResult.clarifying_questions[0]);
        setPendingClarifyingQueue(intentResult.clarifying_questions);
        setPendingClarifyingAnswers([]);
      } else {
        setPendingClarifyingQueue([]);
        setPendingClarifyingAnswers([]);
        assistantMessage = {
          id: `ai-${Date.now()}`,
          role: "assistant",
          text:
            locale === "zh-TW"
              ? "我有一套很適合你的方向，這是幫你搭好的一套。"
              : "I have a direction in mind — here's the outfit I'd start with.",
          recommendation: await adaptToChatRecommendation(
            await fetchRecommendation(intentResult.session_id, token),
            token,
          ),
        };
      }

      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      nextConversation = conversationService.update({ ...latest, engineSessionId: intentResult.session_id });
      nextConversation = conversationService.appendMessage(nextConversation, assistantMessage);
      persistConversation(nextConversation);
    } catch (error) {
      console.error("[stylist] 呼叫 ENGINE01／ENGINE02 失敗：", error);
      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      nextConversation = conversationService.appendMessage(latest, {
        id: `ai-${Date.now()}`,
        role: "assistant",
        text:
          locale === "zh-TW"
            ? "後端目前連不上，稍後再試一次，或確認 ENGINE01／ENGINE02 服務都已經啟動。"
            : "Couldn't reach the backend just now — please try again, or check that ENGINE01/ENGINE02 are running.",
      });
      persistConversation(nextConversation);
    } finally {
      setIsGenerating(false);
    }
  }

  // 使用者實際打字送出、或點某個 quickChoice/visualChoice 按鈕都會走到這裡
  // （`onChoice={sendPrompt}`，見下面 render 那段）。多數情況下就是直接組一個
  // 使用者訊息泡泡、呼叫 runIntentTurn() 打後端；但如果目前正卡在一批多題
  // 的 clarifying-question 佇列中間（pendingClarifyingQueue 非空——見
  // runIntentTurn() 設定它的地方），這通常代表使用者剛回答的是佇列裡的
  // 「目前顯示中」那一題，不能立刻打後端，要先在本地依序秀出佇列裡剩下
  // 的題目，全部答完才把收集到的答案合併成一句話真正送出 /intent。
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

    if (pendingClarifyingQueue.length > 0) {
      const accumulatedAnswers = [...pendingClarifyingAnswers, trimmed];
      const remainingQueue = pendingClarifyingQueue.slice(1);

      if (remainingQueue.length > 0) {
        // 佇列裡還有題目沒問——秀出下一題，先不打後端。
        nextConversation = conversationService.appendMessage(
          nextConversation,
          adaptToClarifyingMessage(remainingQueue[0]),
        );
        persistConversation(nextConversation);
        setPendingClarifyingQueue(remainingQueue);
        setPendingClarifyingAnswers(accumulatedAnswers);
        return;
      }

      // 這是這批問題的最後一題，答案都收集齊了，合併成一句話真正送出去。
      setPendingClarifyingQueue([]);
      setPendingClarifyingAnswers([]);
      void runIntentTurn(accumulatedAnswers.join(locale === "zh-TW" ? "；" : "; "), nextConversation);
      return;
    }

    void runIntentTurn(trimmed, nextConversation);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendPrompt(input);
  }

  function preferenceContext(messageId?: string) {
    return {
      conversationId: activeConversation?.id,
      messageId,
      roundKey: messageId,
    };
  }

  function handleFeedback(item: FashionRecommendation, value: "dislike") {
    const user = authService.getSession();

    if (!user || !activeConversation || isGenerating || value !== "dislike") {
      return;
    }

    setPreferenceState(preferenceService.toggleDislikedItem(user.id, item, preferenceContext()));
  }

  async function saveVirtualYou(photo: File | null, measurements: VirtualYouMeasurements) {
    const user = authService.getSession();

    if (!user) {
      router.replace("/login");
      return;
    }

    setVirtualYouStorageError("");

    try {
      replaceVirtualYou(await virtualYouService.save(user.id, photo, measurements));
      setVirtualYouModalOpen(false);
    } catch {
      setVirtualYouStorageError(t.virtualYou.storageError);
    }
  }

  async function saveCreateYou({
    originalUserImage,
    extractedPersonImage,
    personBoundingBox,
  }: {
    originalUserImage: Blob;
    extractedPersonImage: Blob;
    personBoundingBox: NonNullable<VirtualYouProfile["personBoundingBox"]>;
  }) {
    const user = authService.getSession();

    if (!user) {
      console.warn("[CreateYou] Cannot save extracted person: no authenticated user");
      router.replace("/login");
      return null;
    }

    console.log("[CreateYou] Saving extracted Virtual You asset", {
      originalUserImageSize: originalUserImage.size,
      extractedPersonImageSize: extractedPersonImage.size,
      personBoundingBox,
    });

    return virtualYouService.saveExtractedPerson({
      userId: user.id,
      originalUserImage,
      extractedPersonImage,
      personBoundingBox,
    });
  }

  async function handleCreateYouUpload(file: File) {
    console.log("[CreateYou] Starting upload", {
      name: file.name,
      type: file.type,
      size: file.size,
    });
    setCreateYouProcessing(true);
    setCreateYouError("");

    try {
      const virtualYouAssets = await uploadUserPhoto(file);
      replaceVirtualYou(await saveCreateYou(virtualYouAssets));
      setTryOnState({ topOrDress: null, bottom: null });
      replaceActiveTryOnImage(null);
      setStyledMessage(null);
      setTryOnStatus("idle");
      setTryOnError("");
      console.log("[CreateYou] Rendering extracted person");
    } catch (error) {
      const code = getCreateYouErrorCode(error);
      console.error("[CreateYou] Pipeline failed", {
        code,
        details: error instanceof CreateYouError ? error.details : undefined,
        error,
      });

      if (code === "missing_api_key") {
        setCreateYouError(t.virtualYou.extractionConfigError);
      } else if (code === "invalid_image") {
        setCreateYouError(t.virtualYou.invalidImageError);
      } else if (
        code === "extraction_request_failed" ||
        code === "extraction_response_missing_image" ||
        code === "openai_request_failed" ||
        code === "openai_response_missing_image"
      ) {
        setCreateYouError(t.virtualYou.openAiExtractionError);
      } else if (code === "no_person_detected") {
        setCreateYouError(t.virtualYou.noPersonDetected);
      } else if (code === "background_removal_failed") {
        setCreateYouError(t.virtualYou.backgroundRemovalError);
      } else {
        setCreateYouError(t.virtualYou.imageProcessingError);
      }
    } finally {
      setCreateYouProcessing(false);
    }
  }

  async function useDefaultVirtualYou() {
    const user = authService.getSession();

    if (!user) {
      router.replace("/login");
      return;
    }

    setVirtualYouStorageError("");

    try {
      replaceVirtualYou(await virtualYouService.useDefault(user.id));
      setVirtualYouModalOpen(false);
    } catch {
      setVirtualYouStorageError(t.virtualYou.storageError);
    }
  }

  async function applyTryOnState(nextState: TryOnState, options?: { delayMs?: number; message?: StyledMessage | null }) {
    if (tryOnStatus === "generating") {
      return;
    }

    const wearableItems = [
      nextState.topOrDress,
      isDress(nextState.topOrDress) ? null : nextState.bottom,
    ].filter(Boolean) as FashionRecommendation[];

    if (wearableItems.length === 0) {
      setTryOnState(nextState);
      replaceActiveTryOnImage(null);
      setStyledMessage(options?.message ?? null);
      setTryOnStatus("idle");
      setTryOnError("");
      return;
    }

    setTryOnStatus("generating");
    setTryOnError("");
    setTryOnState(nextState);
    replaceActiveTryOnImage(null);
    setStyledMessage(null);

    try {
      await new Promise((resolve) => window.setTimeout(resolve, options?.delayMs ?? 320));
      const preview = await virtualYouService.generateVirtualTryOn(virtualYou, wearableItems[0]);
      replaceActiveTryOnImage(preview.generatedImageUrl);
      setStyledMessage(options?.message ?? null);
      setTryOnStatus("idle");
    } catch {
      setTryOnState({ topOrDress: null, bottom: null });
      replaceActiveTryOnImage(null);
      setStyledMessage(null);
      setTryOnStatus("error");
      setTryOnError(t.virtualYou.tryOnError);
    }
  }

  async function handleTryOn(item: FashionRecommendation) {
    const slot = getItemSlot(item);

    if (slot === "bottom") {
      if (tryOnState.bottom?.id === item.id) {
        await applyTryOnState({ ...tryOnState, bottom: null }, { message: null });
        return;
      }

      await applyTryOnState({ ...tryOnState, bottom: item }, { message: null });
      return;
    }

    if (tryOnState.topOrDress?.id === item.id) {
      await applyTryOnState({ ...tryOnState, topOrDress: null }, { message: null });
      return;
    }

    await applyTryOnState(
      {
        topOrDress: item,
        bottom: isDress(item) ? null : tryOnState.bottom,
      },
      { message: null },
    );
  }

  async function handleTryOnOutfit(outfit: OutfitRecommendation) {
    await applyTryOnState(
      {
        topOrDress: outfit.items.topOrDress,
        bottom: isDress(outfit.items.topOrDress) ? null : outfit.items.bottom,
      },
      {
        message: {
          title: "Styled for you ✦",
          summary: outfit.name,
          reason: outfit.explanation,
        },
      },
    );
  }

  async function handleDesignForMe(messageId: string) {
    if (!activeConversation || isGenerating || !activeConversation.engineSessionId) {
      return;
    }

    const token = authService.getSessionToken();
    if (!token) {
      return;
    }

    // 生圖進行中鎖住對話輸入框（見 docs/frontend.md 代辦事項 3）：跟一般聊天
    // 打字送出共用同一個 isGenerating 旗標，輸入框／送出鍵本來就是照這個 disable。
    shouldFollowRef.current = true;
    setIsGenerating(true);

    try {
      // 2026-09-19：Hermes Agent 已經確認裝在這台機器的 WSL2 裡、橋接測過真的能生圖
      // （agent/scripts/generate_grid.py 的 _generate() 在 Windows 上會跨進 WSL2 呼叫），
      // 這裡改成 dryRun: false，真的花額度生單品。
      const result = await fetchConceptImage(activeConversation.engineSessionId, token, { dryRun: false });

      const latest =
        conversationService.list(activeConversation.userId).find((c) => c.id === activeConversation.id) ||
        activeConversation;

      if (result.zones) {
        // 整套請求：上衣／下身各一組六格，跟資料庫推薦一樣先秀 Top Pick，
        // 按 Try More 展開兩區各 6 張——重用既有的 ChatRecommendation 顯示殼，
        // 不是 recommendations 那個平鋪清單。
        const recommendation = adaptConceptZonesToChatRecommendation(result);
        const summary =
          locale === "zh-TW"
            ? "生成完成，先幫你配了一套，按「Try More」看上衣／下身各 6 件候選。"
            : "Done — here's a first pairing. Tap Try More for 6 options in each zone.";
        const nextConversation = conversationService.appendMessage(latest, {
          id: `assistant-design-${Date.now()}`,
          role: "assistant",
          text: summary,
          recommendation: recommendation ?? undefined,
        });
        persistConversation(nextConversation);
      } else if (result.concepts) {
        // 單一品項：維持原本的扁平清單顯示。
        const concepts = result.concepts;
        const varietyLines = concepts.cells
          .map((cell) => cell.varied_label)
          .filter((label): label is string => Boolean(label))
          .join("、");

        const summary =
          locale === "zh-TW"
            ? concepts.dry_run
              ? `（測試模式，還沒真的生圖）已經組好六格的生成 prompt，這六格會分別呈現：${varietyLines || "（尚未指定差異）"}。`
              : "生成完成，六件新單品在下面，點一件試穿看看。"
            : concepts.dry_run
              ? `(Dry run — no image generated yet.) The six-cell prompt is ready. Cells will vary: ${varietyLines || "(not yet specified)"}.`
              : "Done — six new pieces below, tap one to try it on.";

        const nextConversation = conversationService.appendMessage(latest, {
          id: `assistant-design-${Date.now()}`,
          role: "assistant",
          text: summary,
          recommendations: concepts.dry_run ? undefined : conceptCellsToRecommendations(concepts),
        });
        persistConversation(nextConversation);
      }
    } catch (error) {
      console.error("[stylist] 呼叫 ENGINE01 /concept-image 失敗：", error);
      const latest =
        conversationService.list(activeConversation.userId).find((c) => c.id === activeConversation.id) ||
        activeConversation;
      const message = error instanceof StylistApiError ? error.message : null;
      const nextConversation = conversationService.appendMessage(latest, {
        id: `assistant-design-error-${Date.now()}`,
        role: "assistant",
        text:
          locale === "zh-TW"
            ? `生成新單品失敗：${message ?? "請確認 ENGINE01 服務是否已啟動"}`
            : `Couldn't generate new pieces: ${message ?? "please check ENGINE01 is running"}`,
      });
      persistConversation(nextConversation);
    } finally {
      setIsGenerating(false);
      handleRecommendationBackToTopPick(messageId);
    }
  }

  function handleRecommendationNavigate(messageId: string, slot: "topOrDress" | "bottom", index: number) {
    setRecommendationStateByMessageId((current) => {
      const state = current[messageId];

      if (!state) {
        return current;
      }

      return {
        ...current,
        [messageId]: {
          ...state,
          alternatives: {
            ...state.alternatives,
            selectedTopOrDressIndex: slot === "topOrDress" ? index : state.alternatives.selectedTopOrDressIndex,
            selectedBottomIndex: slot === "bottom" ? index : state.alternatives.selectedBottomIndex,
          },
        },
      };
    });
  }

  function handleRecommendationRate(
    messageId: string,
    itemId: string,
    dimension: PreferenceRatingDimension,
    rating: number,
  ) {
    const user = authService.getSession();

    if (!user) {
      return;
    }

    setPreferenceState(preferenceService.setDimensionRating(user.id, itemId, dimension, rating));
  }

  function handleRecommendationToggleSaved(messageId: string, item: FashionRecommendation) {
    const user = authService.getSession();

    if (!user) {
      return;
    }

    setPreferenceState(preferenceService.toggleSavedItem(user.id, item, preferenceContext(messageId)));
  }

  function handleRecommendationSaveLook(messageId: string) {
    const user = authService.getSession();
    const state = recommendationStateByMessageId[messageId];

    if (!user || !state?.topPick) {
      return;
    }

    setPreferenceState(preferenceService.toggleSavedOutfitItems(user.id, state.topPick, preferenceContext(messageId)));
  }

  function handleRecommendationTryMore(messageId: string) {
    setRecommendationStateByMessageId((current) => {
      const state = current[messageId];

      if (!state) {
        return current;
      }

      return {
        ...current,
        [messageId]: {
          ...state,
          view: "explore",
        },
      };
    });
  }

  function handleRecommendationBackToTopPick(messageId: string) {
    setRecommendationStateByMessageId((current) => {
      const state = current[messageId];

      if (!state) {
        return current;
      }

      return {
        ...current,
        [messageId]: {
          ...state,
          view: "top-pick",
        },
      };
    });
  }

  function handleTryOnFeedback(feedbackValue: "like" | "dislike") {
    const user = authService.getSession();
    const canRateTryOn = Boolean(tryOnState.topOrDress && (isDress(tryOnState.topOrDress) || tryOnState.bottom));

    if (!user || !canRateTryOn) {
      return;
    }

    setPreferenceState(preferenceService.setTryOnFeedback(user.id, activeTryOnItems, feedbackValue, preferenceContext()));
  }

  const feedback = useMemo(() => {
    const next: Record<string, "like" | "dislike"> = {};

    Object.keys(preferenceState.savedItems).forEach((itemId) => {
      next[itemId] = "like";
    });
    Object.keys(preferenceState.dislikedItems).forEach((itemId) => {
      next[itemId] = "dislike";
    });

    return next;
  }, [preferenceState.dislikedItems, preferenceState.savedItems]);
  const signals = activeConversation?.preferenceSignals || [];
  const activeTryOnOutfitKey = outfitKeyFromItems(activeTryOnItems);
  const activeTryOnFeedback = activeTryOnOutfitKey ? preferenceState.tryOnFeedback[activeTryOnOutfitKey]?.feedback : undefined;

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
              onToggleSaved={handleRecommendationToggleSaved}
              onTryOn={handleTryOn}
              onTryOnOutfit={handleTryOnOutfit}
              onRecommendationNavigate={handleRecommendationNavigate}
              onRecommendationTryMore={handleRecommendationTryMore}
              onRecommendationBackToTopPick={handleRecommendationBackToTopPick}
              onRecommendationRate={handleRecommendationRate}
              onRecommendationToggleSaved={handleRecommendationToggleSaved}
              onRecommendationSaveLook={handleRecommendationSaveLook}
              onDesignForMe={handleDesignForMe}
              choicesDisabled={index !== activeConversation.messages.length - 1 || isGenerating}
              feedback={feedback}
              preferenceState={preferenceState}
              activeTryOnItemIds={activeTryOnItemIds}
              recommendationState={recommendationStateByMessageId[message.id]}
              tryOnState={tryOnState}
              tryOnStatus={tryOnStatus}
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
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                voiceState === "recording"
                  ? t.stylist.voiceListening
                  : voiceState === "transcribing"
                    ? t.stylist.voiceTranscribing
                    : t.stylist.input
              }
              className="h-12 min-w-0 flex-1 border border-input bg-background px-4 text-sm outline-none transition focus:border-primary"
            />
            {voiceState === "recording" && (
              <div className="hidden h-12 items-center gap-2 border border-border bg-background px-3 text-sm text-muted-foreground sm:flex">
                <span className="size-2 rounded-full bg-destructive" />
                <span>{t.stylist.voiceListening}</span>
                <span className="tabular-nums">{formatVoiceTime(voiceElapsedSeconds)}</span>
              </div>
            )}
            {voiceState === "transcribing" && (
              <div className="hidden h-12 items-center border border-border bg-background px-3 text-sm text-muted-foreground sm:flex">
                {t.stylist.voiceTranscribing}
              </div>
            )}
            {voiceState === "recording" ? (
              <Button type="button" size="icon-lg" variant="outline" onClick={stopVoiceRecording} aria-label={t.stylist.voiceStop}>
                <Square className="size-4 fill-current" />
              </Button>
            ) : (
              <Button
                type="button"
                size="icon-lg"
                variant="outline"
                onClick={startVoiceRecording}
                aria-label={t.stylist.voiceInput}
                disabled={voiceState === "transcribing" || isGenerating}
              >
                <Mic className="size-4" />
              </Button>
            )}
            <Button type="submit" size="lg" aria-label={t.stylist.send} disabled={isGenerating}>
              <Send className="size-4" />
              {t.stylist.send}
            </Button>
          </div>
          {voiceState === "recording" && (
            <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground sm:hidden">
              <span className="size-2 rounded-full bg-destructive" />
              <span>{t.stylist.voiceListening}</span>
              <span className="tabular-nums">{formatVoiceTime(voiceElapsedSeconds)}</span>
            </div>
          )}
          {voiceState === "transcribing" && <p className="mt-2 text-sm text-muted-foreground">{t.stylist.voiceTranscribing}</p>}
          {voiceError && <p className="mt-2 text-sm text-destructive">{voiceError}</p>}
        </form>
      </section>

      <StylePanel
        signals={signals}
        feedbackCount={Object.keys(feedback).length}
        styleProfile={styleProfile}
        virtualYou={virtualYou}
        createYouProcessing={createYouProcessing}
        createYouError={createYouError}
        onCreateYouUpload={handleCreateYouUpload}
        activeTryOnImage={activeTryOnImage}
        activeTryOnOverlays={activeTryOnOverlays}
        tryOnStatus={tryOnStatus}
        tryOnError={tryOnError}
        activeTryOnFeedback={activeTryOnFeedback}
        onTryOnFeedback={handleTryOnFeedback}
        canShowTryOnFeedback={canShowTryOnFeedback}
        styledMessage={styledMessage}
      />
      <VirtualYouModal
        key={virtualYouModalOpen ? virtualYou?.updatedAt || "new-virtual-you" : "closed-virtual-you"}
        open={virtualYouModalOpen}
        onClose={() => setVirtualYouModalOpen(false)}
        onSave={saveVirtualYou}
        onUseDefault={useDefaultVirtualYou}
        initialProfile={virtualYou}
        storageError={virtualYouStorageError}
      />
    </div>
  );
}
