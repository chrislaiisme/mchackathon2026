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
  Sparkles,
  Square,
  Star,
  ThumbsDown,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { OutfitPairError, pairOutfit, type OutfitPairing } from "@/lib/services/outfit-pair";
import {
  createChatRecommendation,
  createStylistReply,
} from "@/lib/mock/stylist";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import { onboardingService, type OnboardingProfile } from "@/lib/services/onboarding";
import { outfitKeyFromItems, preferenceService } from "@/lib/services/preferences";
import {
  adaptPreferencesToFeedbackRequest,
  adaptToChatRecommendation,
  adaptToClarifyingMessage,
  fetchConceptImage,
  conceptCellsToRecommendations,
  fetchIntentTurn,
  fetchRecommendation,
  fetchRecommendationReasonRewrite,
  submitFeedback,
  StylistApiError,
  type BackendClarifyingQuestion,
  type ZoneByItemId,
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
  GeneratedGroup,
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
  const { t, locale } = useI18n();

  return (
    <article className="group overflow-hidden border border-border bg-card">
      <div
        className={cn(
          "fashion-image aspect-[3/4] bg-muted transition duration-700",
          // 生成的是白底平拍圖，整件衣服就是畫面全部——放大會把袖子褲管推出框外。
          item.generated ? "fashion-image--contain" : "group-hover:scale-[1.03]",
        )}
        style={{ backgroundImage: `url(${item.imageUrl})` }}
        aria-label={item.name}
      />
      <div className="space-y-4 p-4">
        <div>
          {item.generated ? (
            // 生成單品的標記比「94% match」長得多，跟標題並排會被擠掉，所以另起一行。
            <>
              <p className="text-[0.68rem] uppercase tracking-[0.18em] text-muted-foreground">
                {locale === "zh-TW" ? "AI 生成 · 非商品庫" : "AI generated · not in catalog"}
              </p>
              <h3 className="mt-2 font-serif text-xl leading-tight text-foreground">{item.name}</h3>
            </>
          ) : (
            <div className="flex items-start justify-between gap-4">
              <h3 className="font-serif text-xl leading-tight text-foreground">{item.name}</h3>
              <span className="mt-1 shrink-0 border-b border-primary/50 pb-1 text-xs text-muted-foreground">
                {item.confidence}% {t.stylist.match}
              </span>
            </div>
          )}
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
            {item.generated ? item.priceBand : `${t.stylist.priceBand} ${item.priceBand}`}
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
            <Button
              size="icon-sm"
              variant={saved ? "default" : "outline"}
              aria-label={`Save ${item.name}`}
              onClick={() => onToggleSaved(item)}
            >
              <Bookmark className={`size-4 ${saved ? "fill-current" : ""}`} />
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

/**
 * Design for Me 生出來的兩組單品：左邊上衣、右邊下裝，各自一個輪播。
 *
 * 跟 ENGINE 02 的 explore 檢視用同一支 RecommendationCarousel，所以六件是翻頁
 * 看而不是攤成一排，試穿／愛心／評分／收藏也自動一致。翻到第幾件跟星等是純
 * 畫面狀態，留在這支元件裡；收藏與喜好要跨元件累積，由上層傳進來。
 */
/** 生成的與商品庫的候選接在一起時去重；id 前綴不同（top-ai- / 商品 id），不會誤殺。 */
function dedupeById(items: FashionRecommendation[]): FashionRecommendation[] {
  const seen = new Set();
  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false;
    }
    seen.add(item.id);
    return true;
  });
}

function GeneratedGroupCarousels({
  groups,
  catalogCandidates,
  onPairOutfit,
  onTryOn,
  onFeedback,
  activeTryOnItemIds,
  tryOnStatus,
  feedback,
  preferenceState,
  onToggleSaved,
}: {
  groups: GeneratedGroup[];
  /**
   * 同一輪 ENGINE 02 從商品庫撈到的候選。不畫出來，只進「AI 幫我搭」的候選池——
   * 使用者常常只是不滿意其中一件，這時答案是「現貨上衣 ＋ 生成褲子」。
   */
  catalogCandidates?: { topOrDress: FashionRecommendation[]; bottom: FashionRecommendation[] };
  /** 「AI 幫我搭」：上層補上 intent 與 session 去呼叫配對服務，失敗時 throw。 */
  onPairOutfit: (
    tops: FashionRecommendation[],
    bottoms: FashionRecommendation[],
  ) => Promise<OutfitPairing>;
  onTryOn: (item: FashionRecommendation) => void;
  onFeedback: (item: FashionRecommendation, value: "dislike") => void;
  activeTryOnItemIds: string[];
  tryOnStatus: TryOnStatus;
  feedback: Record<string, "like" | "dislike">;
  /** main 2026-09-20 的統一偏好狀態；收藏與評分都從這裡讀，不再自己維護一份。 */
  preferenceState: UserPreferenceState;
  onToggleSaved: (item: FashionRecommendation) => void;
}) {
  const { locale } = useI18n();
  const [indexBySlot, setIndexBySlot] = useState<Record<string, number>>({});
  const [ratings, setRatings] = useState<Record<string, PreferenceDimensionRatings>>({});
  // 配對結果只是這一輪的畫面狀態，跟翻到第幾件一樣留在這支元件裡：同一個對話可能
  // 有好幾輪 Design for Me，各自的配對互不相干，放到上層反而要多一層 messageId 對照。
  const [pairing, setPairing] = useState<OutfitPairing | null>(null);
  const [pairBusy, setPairBusy] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);

  // 左邊固定上衣、右邊固定下裝，不跟著後端回傳的順序跑。
  const ordered = (["top", "bottom"] as const)
    .map((slot) => groups.find((group) => group.slot === slot))
    .filter((group): group is GeneratedGroup => Boolean(group) && group!.items.length > 0);

  if (ordered.length === 0) {
    return null;
  }

  // 輪播只畫生成的單品——那兩欄的標題就是「不是商品庫裡的商品」，混進現貨會自相矛盾。
  const generatedTops = ordered.find((group) => group.slot === "top")?.items ?? [];
  const generatedBottoms = ordered.find((group) => group.slot === "bottom")?.items ?? [];

  // 但配對的候選池要含商品庫：只換一件是常見情境，池子只有生成的就選不到正解。
  // 去重以 id 為準（兩邊 id 前綴不同，不會誤殺）。
  const tops = dedupeById([...generatedTops, ...(catalogCandidates?.topOrDress ?? [])]);
  const bottoms = dedupeById([...generatedBottoms, ...(catalogCandidates?.bottom ?? [])]);

  async function handlePairClick() {
    if (pairBusy) {
      return;
    }
    setPairBusy(true);
    setPairError(null);
    try {
      const result = await onPairOutfit(tops, bottoms);
      // 只有選中的那件真的在輪播裡（＝生成的）才翻得動；選到現貨時 index 是 -1，
      // 輪播維持原樣，改由下面的結果卡把兩件一起畫出來。
      const topIndex = generatedTops.findIndex((item) => item.id === result.top.id);
      const bottomIndex = generatedBottoms.findIndex((item) => item.id === result.bottom.id);
      // 主要的回饋是兩個輪播各自翻到選中的那一件——直接看到兩件並排比讀一段文字快。
      setIndexBySlot((state) => ({
        ...state,
        ...(topIndex >= 0 ? { top: topIndex } : {}),
        ...(bottomIndex >= 0 ? { bottom: bottomIndex } : {}),
      }));
      setPairing(result);
    } catch (error) {
      // 就地顯示，輪播維持原樣：這一輪的試穿、愛心、收藏都還要能用。
      console.error("[stylist] AI 幫我搭失敗：", error);
      setPairError(error instanceof Error ? error.message : String(error));
    } finally {
      setPairBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
          {locale === "zh-TW" ? "AI 生成，不是商品庫裡的商品" : "AI generated, not in the catalog"}
        </p>
        {/* 兩邊都有東西才配得起來；只生出一邊時（另一邊生圖失敗）不給這顆按鈕。 */}
        {tops.length > 0 && bottoms.length > 0 && (
          <Button type="button" size="sm" onClick={handlePairClick} disabled={pairBusy}>
            <Sparkles className="size-4" />
            {pairBusy
              ? locale === "zh-TW"
                ? "配對中…"
                : "Styling…"
              : locale === "zh-TW"
                ? "AI 幫我搭"
                : "Style it for me"}
          </Button>
        )}
      </div>

      {pairing && (
        <div className="border-l border-primary pl-4 text-sm leading-6 text-foreground">
          {/* 退場的組合不是 AI 挑的，照實講——講成 AI 的判斷會讓人以為第一件配第一件
              有什麼道理。 */}
          {pairing.source === "fallback" && (
            <p className="text-muted-foreground">
              {locale === "zh-TW"
                ? "AI 沒回應，先給你一組保守的搭配："
                : "The stylist did not answer — here is a safe pairing instead:"}
            </p>
          )}
          <p>
            {pairing.reason ||
              (locale === "zh-TW" ? "第一件上衣配第一件下身。" : "The first top with the first bottom.")}
          </p>

          {/* 選中的那兩件一定要畫出來：可能其中一件是商品庫的現貨，不在下面的輪播裡，
              只翻輪播的話使用者根本看不到 AI 挑了什麼。 */}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {[pairing.top, pairing.bottom].map((item) => (
              <figure key={item.id} className="flex items-center gap-3 border border-border bg-card p-2">
                <div
                  className={cn(
                    "fashion-image size-16 shrink-0 bg-muted",
                    item.generated && "fashion-image--contain",
                  )}
                  style={{ backgroundImage: `url(${item.imageUrl})` }}
                  role="img"
                  aria-label={item.name}
                />
                <figcaption className="min-w-0">
                  <p className="text-[0.68rem] uppercase tracking-[0.18em] text-muted-foreground">
                    {item.generated
                      ? locale === "zh-TW" ? "AI 生成" : "AI generated"
                      : locale === "zh-TW" ? "商品庫現貨" : "In the catalog"}
                  </p>
                  <p className="truncate text-sm text-foreground">{item.name}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      {pairError && (
        <p className="text-sm leading-6 text-destructive">
          {locale === "zh-TW" ? `配對失敗：${pairError}` : `Pairing failed: ${pairError}`}
        </p>
      )}

      <div className="grid items-stretch gap-5 xl:grid-cols-2">
        {ordered.map((group) => {
          // 這一組只有幾件，index 取餘數以防萬一（例如某一邊生失敗只回了幾格）。
          const index = (indexBySlot[group.slot] ?? 0) % group.items.length;
          const current = group.items[index];

          return (
            <RecommendationCarousel
              key={group.slot}
              title={group.label}
              items={group.items}
              index={index}
              onNavigate={(nextIndex) =>
                setIndexBySlot((state) => ({ ...state, [group.slot]: nextIndex }))
              }
              onTryOn={onTryOn}
              onFeedback={onFeedback}
              activeTryOnItemIds={activeTryOnItemIds}
              tryOnStatus={tryOnStatus}
              feedback={feedback}
              rating={ratings[current.id]}
              onRate={(itemId, dimension, value) =>
                setRatings((state) => ({
                  ...state,
                  [itemId]: { ...(state[itemId] ?? {}), [dimension]: value },
                }))
              }
              saved={Boolean(preferenceState.savedItems[current.id])}
              onToggleSaved={onToggleSaved}
            />
          );
        })}
      </div>
    </div>
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
  onPairOutfit,
  designBusy,
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
  onPairOutfit: (
    tops: FashionRecommendation[],
    bottoms: FashionRecommendation[],
  ) => Promise<OutfitPairing>;
  designBusy?: boolean;
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

      {/* Design for Me 生出來的單品自成一輪，左邊上衣、右邊下裝，各自輪播。
          用的是跟 ENGINE 02 explore 檢視同一支 RecommendationCarousel，所以
          試穿、愛心、評分、收藏都在；差別只有卡片上標著「非商品庫」。 */}
      {message.generatedGroups && message.generatedGroups.length > 0 && (
        <GeneratedGroupCarousels
          groups={message.generatedGroups}
          catalogCandidates={message.catalogCandidates}
          onPairOutfit={onPairOutfit}
          onTryOn={onTryOn}
          onFeedback={onFeedback}
          activeTryOnItemIds={activeTryOnItemIds}
          tryOnStatus={tryOnStatus}
          feedback={feedback}
          preferenceState={preferenceState}
          onToggleSaved={(item) => onToggleSaved(message.id, item)}
        />
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
          designBusy={designBusy}
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

function applyRecommendationReasonRewrites(
  recommendation: ChatRecommendation,
  rewrites: Record<string, string>,
): ChatRecommendation {
  const replaceItem = (item: FashionRecommendation | null): FashionRecommendation | null => {
    if (!item || !rewrites[item.id]) {
      return item;
    }
    return { ...item, explanation: rewrites[item.id] };
  };

  const topOrDress = replaceItem(recommendation.topPick.items.topOrDress);
  const bottom = replaceItem(recommendation.topPick.items.bottom);
  return {
    ...recommendation,
    topPick: {
      ...recommendation.topPick,
      items: { topOrDress: topOrDress as FashionRecommendation, bottom },
      explanation: topOrDress?.explanation || recommendation.topPick.explanation,
    },
    alternatives: {
      ...recommendation.alternatives,
      topOrDressCandidates: recommendation.alternatives.topOrDressCandidates.map((item) => replaceItem(item) as FashionRecommendation),
      bottomCandidates: recommendation.alternatives.bottomCandidates.map((item) => replaceItem(item) as FashionRecommendation),
    },
  };
}

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

// 這個 catch 以前不管什麼錯都說「後端連不上」。實際上多數失敗是後端好端端回了
// 200、但資料不合我們的預期（例如某一區沒有商品），把它講成連線問題會讓人往完全
// 錯的方向查——2026-09-19 就因為這句話，花了很久才發現真正的原因是 ENGINE02 的
// port 指錯。只有真的連不出去（fetch 自己丟的 TypeError）才講連線。
function describeTurnFailure(error: unknown, locale: string): string {
  if (error instanceof TypeError) {
    return locale === "zh-TW"
      ? "後端目前連不上，稍後再試一次，或確認 ENGINE01／ENGINE02 服務都已經啟動。"
      : "Couldn't reach the backend just now — please try again, or check that ENGINE01/ENGINE02 are running.";
  }

  const detail =
    error instanceof StylistApiError || error instanceof Error ? error.message : String(error);

  return locale === "zh-TW" ? `這一輪沒有結果：${detail}` : `This turn came back empty: ${detail}`;
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
  const { t, locale } = useI18n();

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
          className={cn(
            "fashion-image relative h-[320px] bg-muted transition duration-500 sm:h-[360px] xl:h-[400px]",
            item.generated && "fashion-image--contain",
          )}
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
                {item.generated
                  ? locale === "zh-TW" ? "AI 生成 · 非商品庫" : "AI generated · not in catalog"
                  : `${item.confidence}% ${t.stylist.match}`}
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
  designBusy,
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
  designBusy?: boolean;
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
      generated: outfit.items.topOrDress.generated,
    },
    ...(hasBottom && outfit.items.bottom
      ? [
          {
            id: outfit.items.bottom.id,
            label: "Bottom",
            eyebrow: "Stylist's Pick",
            name: outfit.items.bottom.name,
            imageUrl: outfit.items.bottom.imageUrl,
            generated: outfit.items.bottom.generated,
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
              className={cn(
                "fashion-image relative h-[320px] bg-muted sm:h-[440px]",
                panel.generated && "fashion-image--contain",
              )}
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
              {/* 商品庫裡沒有想要的 → 讓 AI 生幾件。TOP 跟 BOTTOM 兩張六宮格並行生，
                  現場約 50–70 秒。樣式跟 Enterprise Insights 的「Ask Your Market」
                  一致（實心主色＋Sparkles）——同一套產品裡，叫 AI 做事的入口要長一樣，
                  使用者才認得出哪些按鈕會花時間、會產生新東西。
                  兩個停用條件都要：designBusy 是這一次生成還沒回來，
                  designForMeDisabled 是這則訊息已經不是最後一則（main 2026-09-20 加的）。 */}
              <Button
                type="button"
                size="sm"
                onClick={onDesignForMe}
                disabled={designBusy || designForMeDisabled}
              >
                <Sparkles className="size-4" />
                {designBusy ? t.stylist.generating : "Design for Me"}
              </Button>
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
  designBusy,
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
  designBusy?: boolean;
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
        designBusy={designBusy}
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
  waitingLabel,
}: {
  baseImage: string;
  displayImage: string;
  tryOnOverlays: TryOnOverlay[];
  isTryingOn: boolean;
  loadingLabel: string;
  waitingLabel: string;
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
        <div
          className="absolute inset-x-0 top-1/2 z-20 flex -translate-y-1/2 justify-center px-4"
          role="status"
          aria-live="polite"
        >
          <div className="flex max-w-full flex-col items-center rounded-full border border-background/70 bg-background/80 px-5 py-4 text-center shadow-[0_10px_30px_rgba(26,22,35,0.12)] backdrop-blur-sm">
            <span
              className="mb-2 size-4 animate-spin rounded-full border-2 border-primary/25 border-t-primary"
              aria-hidden="true"
            />
            <p className="max-w-full text-sm font-semibold uppercase tracking-[0.12em] text-foreground sm:text-base">
              {loadingLabel}
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground sm:text-sm">{waitingLabel}</p>
          </div>
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
          waitingLabel={t.virtualYou.tryOnWait}
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
  // ENGINE 01 最近一輪抽出來的意圖。生成單品要用它，所以每次問到就留下來。
  const [lastIntent, setLastIntent] = useState<Record<string, unknown> | null>(null);
  const [isGeneratingItems, setIsGeneratingItems] = useState(false);
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

  async function applyBackgroundReasonRewrite(
    conversationId: string,
    messageId: string,
    sessionId: string,
    token: string,
  ) {
    try {
      const rewrites = await fetchRecommendationReasonRewrite(sessionId, token);
      if (Object.keys(rewrites).length === 0) {
        return;
      }

      const current = conversationService.list(authService.getSession()?.id || "").find((item) => item.id === conversationId);
      if (!current) {
        return;
      }
      const next = conversationService.update({
        ...current,
        messages: current.messages.map((message) =>
          message.id === messageId && message.recommendation
            ? { ...message, recommendation: applyRecommendationReasonRewrites(message.recommendation, rewrites) }
            : message,
        ),
      });
      persistConversation(next);
      setRecommendationStateByMessageId((currentState) => {
        const existing = currentState[messageId];
        return existing
          ? { ...currentState, [messageId]: applyRecommendationReasonRewrites(existing, rewrites) }
          : currentState;
      });
    } catch (error) {
      // 改寫只是可選的文案增強；保留立即顯示的 ENGINE02 template reason。
      console.warn("[stylist] ENGINE02 推薦理由背景改寫未完成：", error);
    }
  }

  // 2026-09-19 新增：把上一輪（conversation.engineRound）收集到的
  // preferenceState 收藏／不喜歡／打分／整套喜歡送給 ENGINE03。沒有
  // engineSessionId／engineRound（還沒有真的跑過一輪）或這輪完全沒有任何
  // recommendation 訊息就直接跳過，不報錯——這是「有沒有東西可以送」的
  // 正常情況，不是失敗。任何呼叫失敗只印 log，不往外丟例外：這是輔助性的
  // 背景送出，絕對不能卡住使用者發送下一句話。
  async function submitPendingRoundFeedback(conversation: Conversation, token: string) {
    if (!conversation.engineSessionId || conversation.engineRound === undefined) {
      return;
    }

    const lastRecommendationMessage = [...conversation.messages].reverse().find((message) => message.recommendation);
    const recommendation = lastRecommendationMessage?.recommendation;
    if (!recommendation) {
      return;
    }

    // 從 Top Pick／Try More 候選清單重建「這個 id 屬於哪一區」——整套喜歡
    // 一定要分清楚 top_item_id／bottom_item_id，不能只知道兩件不知道哪件是哪區。
    const zoneByItemId: ZoneByItemId = {};
    recommendation.alternatives.topOrDressCandidates.forEach((item) => {
      zoneByItemId[item.id] = "top";
    });
    recommendation.alternatives.bottomCandidates.forEach((item) => {
      zoneByItemId[item.id] = "bottom";
    });
    if (recommendation.topPick.items.topOrDress) {
      zoneByItemId[recommendation.topPick.items.topOrDress.id] = "top";
    }
    if (recommendation.topPick.items.bottom) {
      zoneByItemId[recommendation.topPick.items.bottom.id] = "bottom";
    }

    const { itemFeedbacks, outfitFeedbacks } = adaptPreferencesToFeedbackRequest(preferenceState, zoneByItemId);
    if (itemFeedbacks.length === 0 && outfitFeedbacks.length === 0) {
      return;
    }

    try {
      await submitFeedback(
        conversation.engineSessionId,
        conversation.engineRound,
        itemFeedbacks,
        outfitFeedbacks,
        token,
      );
    } catch (error) {
      // Feedback 是下一輪排序的輔助訊號。舊版快取可能含有已不再屬於這輪
      // session 的生成 item id；後端會安全地拒絕它，但不應讓 Next dev overlay
      // 把這個已處理的情況誤顯示成應用程式崩潰。
      console.warn("[stylist] 送出上一輪回饋已略過（不影響本輪對話）：", error);
    }
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


    // 2026-09-19 新增：送出這輪新訊息之前，先把上一輪收集到的收藏／不喜歡／
    // 打分／整套喜歡送給 ENGINE03——fire-and-forget，任何失敗只印 log，
    // 絕對不能讓回饋送不出去卡住使用者這輪新的對話。用 baseConversation
    // （呼叫端傳進來的，還沒被下面的 /intent 回應覆寫 engineSessionId／
    // engineRound）才是「上一輪」真正的狀態。
    // 回饋要先成功寫回 ENGINE01 session，下一次 /recommend 才能吃到 ENGINE03
    // 的權重調整；submitPendingRoundFeedback 會自行處理失敗，不會阻斷對話。
    await submitPendingRoundFeedback(baseConversation, token);

    try {
      const intentResult = await fetchIntentTurn(nextConversation.engineSessionId, messageForBackend, token);
      // Design for Me／AI 幫我搭都要用這包意圖；重整後 React state 會歸零，
      // 所以下面 conversationService.update 時也會一起寫進對話。
      setLastIntent(intentResult.intent ?? null);

      let assistantMessage: ChatMessage;
      let reasonRewriteSessionId: string | null = null;
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
        const zonedRecommendation = await fetchRecommendation(intentResult.session_id, token);
        assistantMessage = {
          id: `ai-${Date.now()}`,
          role: "assistant",
          text:
            locale === "zh-TW"
              ? "我有一套很適合你的方向，這是幫你搭好的一套。"
              : "I have a direction in mind — here's the outfit I'd start with.",
          recommendation: await adaptToChatRecommendation(zonedRecommendation, token),
        };
        reasonRewriteSessionId = zonedRecommendation.session_id;
      }

      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      // lastIntent 跟著 engineSessionId／engineRound 一起寫回對話——單靠
      // setLastIntent 的 React state 撐不過重新整理，Design for Me 會在重整後
      // 誤判成「還沒說需求」。
      nextConversation = conversationService.update({
        ...latest,
        engineSessionId: intentResult.session_id,
        engineRound: intentResult.round,
        lastIntent: intentResult.intent ?? null,
      });
      nextConversation = conversationService.appendMessage(nextConversation, assistantMessage);
      persistConversation(nextConversation);
      if (reasonRewriteSessionId && assistantMessage.recommendation) {
        void applyBackgroundReasonRewrite(nextConversation.id, assistantMessage.id, reasonRewriteSessionId, token);
      }
    } catch (error) {
      console.error("[stylist] 呼叫 ENGINE01／ENGINE02 失敗：", error);
      const latest =
        conversationService.list(nextConversation.userId).find((conversation) => conversation.id === nextConversation.id) ||
        nextConversation;
      nextConversation = conversationService.appendMessage(latest, {
        id: `ai-${Date.now()}`,
        role: "assistant",
        text: describeTurnFailure(error, locale),
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
      const preview = await virtualYouService.runVirtualTryOn(virtualYou, wearableItems);
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

  /** 某一輪 ENGINE 02 的候選。只在那一輪真的有推薦結果時才有東西。 */
  function catalogFor(messageId: string) {
    const state = recommendationStateByMessageId[messageId];

    if (!state) {
      return undefined;
    }

    return {
      topOrDress: state.alternatives.topOrDressCandidates,
      bottom: state.alternatives.bottomCandidates,
    };
  }

  /**
   * Design for Me：商品庫裡沒有想要的，就讓 AI 生幾件出來。
   *
   * 走 ENGINE 01 的 /concept-image（不是生圖 BFF 的 8100）。2026-09-20 兩條線
   * 合成一套之後就只剩這一條：ENGINE 01 那支已經做了分區（zones.resolve_zone_for_item_type
   * 認得連身裙——連身裙只生上身那一區，不會硬湊一件下身）、兩區並行生成、
   * 而且把每一格登記進 session，ENGINE 03 的回饋要靠那些 id 才知道使用者按讚的
   * 是哪一格。這些我在 BFF 那邊都沒有或做得比較差，所以 BFF 的 pair 模式退場。
   *
   * 呈現維持這條分支的樣子：兩個並排輪播（左上身、右下身）自成一輪對話，
   * 不用 Top Pick／Try More 殼——那個殼是給「商品庫撈到的一套」用的，
   * 生成的東西是一批可比較的選項，攤成兩欄比較符合它的用途。
   */
  async function handleDesignForMe(messageId: string) {
    if (!activeConversation || isGeneratingItems) {
      return;
    }

    const sessionId = activeConversation.engineSessionId;
    const token = authService.getSessionToken();

    if (!sessionId || !token) {
      persistConversation(
        conversationService.appendMessage(activeConversation, {
          id: `assistant-design-no-session-${Date.now()}`,
          role: "assistant",
          text:
            locale === "zh-TW"
              ? "先說一句你想要什麼，我才知道要生成什麼樣的單品。"
              : "Tell me what you are after first — I need something to design from.",
        }),
      );
      return;
    }

    shouldFollowRef.current = true;
    setIsGeneratingItems(true);
    const conversationId = activeConversation.id;
    const userId = activeConversation.userId;

    function latestConversation() {
      return (
        conversationService.list(userId).find((conversation) => conversation.id === conversationId) ||
        activeConversation!
      );
    }

    try {
      const result = await fetchConceptImage(sessionId, token, { dryRun: false });

      // 連身裙時 zones.bottom.cells 是空陣列（不是欄位缺失），下面過濾掉空的那一組，
      // 畫面就只會出現一個輪播——這正是 main 分區邏輯要的行為。
      const groups: GeneratedGroup[] = ([
        { slot: "top", label: locale === "zh-TW" ? "上身" : "Top" },
        { slot: "bottom", label: locale === "zh-TW" ? "下身" : "Bottom" },
      ] as const)
        .map(({ slot, label }) => ({
          slot,
          label,
          items: conceptCellsToRecommendations(result.zones[slot], slot),
        }))
        .filter((group) => group.items.length > 0);

      if (groups.length === 0) {
        throw new StylistApiError(
          locale === "zh-TW" ? "這次沒有切出任何可用的單品" : "No usable pieces came back this time",
        );
      }

      persistConversation(
        conversationService.appendMessage(latestConversation(), {
          id: `assistant-designed-${Date.now()}`,
          role: "assistant",
          text:
            locale === "zh-TW"
              ? "商品庫裡沒有更合適的了，這幾件是照你的需求生成的——還不存在的衣服。"
              : "Nothing closer in the catalog — these are designed from what you asked for, and do not exist yet.",
          generatedGroups: groups,
          // 把觸發這一輪的那一輪、ENGINE 02 撈到的候選一起帶著。不畫出來，
          // 只在「AI 幫我搭」時當候選——使用者可能只是不滿意其中一件。
          catalogCandidates: catalogFor(messageId),
        }),
      );
    } catch (error) {
      console.error("[stylist] 呼叫 ENGINE01 /concept-image 失敗：", error);
      persistConversation(
        conversationService.appendMessage(latestConversation(), {
          id: `assistant-design-error-${Date.now()}`,
          role: "assistant",
          text:
            locale === "zh-TW"
              ? `生成單品失敗：${error instanceof Error ? error.message : String(error)}`
              : `Generating items failed: ${error instanceof Error ? error.message : String(error)}`,
        }),
      );
    } finally {
      setIsGeneratingItems(false);
    }
  }

  /** 「AI 幫我搭」：補上這一輪的意圖與 session，其餘交給配對服務。 */
  async function handlePairOutfit(tops: FashionRecommendation[], bottoms: FashionRecommendation[]) {
    // 跟 handleDesignForMe 同一個讀法：持久化在對話上的優先，React state 當備胎。
    const intent = activeConversation?.lastIntent ?? lastIntent;

    if (!intent) {
      throw new OutfitPairError(
        locale === "zh-TW"
          ? "找不到這一輪的需求，重新說一次你想要什麼再試一次。"
          : "No intent on this conversation — tell me what you are after and try again.",
      );
    }

    return pairOutfit(intent, tops, bottoms, activeConversation?.engineSessionId);
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
              onPairOutfit={handlePairOutfit}
              designBusy={isGeneratingItems}
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
