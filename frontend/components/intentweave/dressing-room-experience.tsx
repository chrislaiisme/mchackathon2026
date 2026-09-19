"use client";

import Link from "next/link";
import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Plus, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { getOutfitSlot, getSavedWardrobeItems, outfitSlots, wardrobeCategories } from "@/lib/mock/dressing-room";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import { preferenceService } from "@/lib/services/preferences";
import { defaultVirtualYouImage, virtualYouService } from "@/lib/services/virtual-you";
import type { OutfitSlot, User, VirtualYouProfile, WardrobeCategory, WardrobeItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type WardrobeFilter = "all" | WardrobeCategory;
type OutfitState = Partial<Record<OutfitSlot, WardrobeItem>>;

function applyWardrobeItem(outfit: OutfitState, item: WardrobeItem): OutfitState {
  const slot = getOutfitSlot(item.category);

  if (outfit[slot]?.id === item.id) {
    const next = { ...outfit };
    delete next[slot];
    return next;
  }

  if (slot === "dress") {
    const next = { ...outfit, dress: item };
    delete next.top;
    delete next.bottom;
    return next;
  }

  if (slot === "top" || slot === "bottom") {
    const next = { ...outfit, [slot]: item };
    delete next.dress;
    return next;
  }

  return { ...outfit, [slot]: item };
}

async function getImageBounds(image: Blob) {
  const imageBitmap = await createImageBitmap(image);
  const bounds = {
    x: 0,
    y: 0,
    width: imageBitmap.width,
    height: imageBitmap.height,
  };

  imageBitmap.close();
  return bounds;
}

function WardrobeFilters({
  activeFilter,
  onChange,
}: {
  activeFilter: WardrobeFilter;
  onChange: (filter: WardrobeFilter) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="flex flex-wrap gap-2">
      {wardrobeCategories.map((category) => (
        <button
          key={category}
          type="button"
          onClick={() => onChange(category)}
          aria-pressed={activeFilter === category}
          className={cn(
            "border px-3 py-2 text-sm transition focus-visible:border-primary focus-visible:outline-none",
            activeFilter === category
              ? "border-primary bg-primary/5 text-foreground"
              : "border-border bg-card text-muted-foreground hover:border-foreground/40 hover:text-foreground",
          )}
        >
          {t.dressingRoom.filters[category]}
        </button>
      ))}
    </div>
  );
}

function WardrobeItemCard({
  item,
  selected,
  onSelect,
  onRemove,
}: {
  item: WardrobeItem;
  selected: boolean;
  onSelect: (item: WardrobeItem) => void;
  onRemove: (item: WardrobeItem) => void;
}) {
  const { t } = useI18n();

  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      aria-pressed={selected}
      className={cn(
        "group overflow-hidden border bg-card text-left transition focus-visible:border-primary focus-visible:outline-none",
        selected ? "border-primary" : "border-border hover:border-foreground/40",
      )}
    >
      <div className="relative overflow-hidden bg-muted">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRemove(item);
          }}
          aria-label={`${t.dressingRoom.remove} ${item.name}`}
          className="absolute right-3 top-3 z-10 inline-flex size-8 items-center justify-center border border-border bg-background/90 text-muted-foreground shadow-sm backdrop-blur transition hover:border-destructive hover:text-destructive focus-visible:border-primary focus-visible:outline-none"
        >
          <X className="size-4" />
        </button>
        <div
          className="fashion-image aspect-[3/4] transition duration-700 group-hover:scale-[1.02]"
          style={{ backgroundImage: `url(${item.imageUrl})` }}
        />
        {selected && (
          <span className="absolute left-3 top-3 inline-flex size-7 items-center justify-center border border-primary bg-background text-primary">
            <Check className="size-4" />
            <span className="sr-only">{t.dressingRoom.selected}</span>
          </span>
        )}
      </div>
      <div className="space-y-2 p-4">
        <div className="font-serif text-xl leading-tight text-foreground">{item.name}</div>
        <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          {item.brand || t.dressingRoom.filters[item.category]}
        </div>
      </div>
    </button>
  );
}

function SavedWardrobe({
  items,
  activeFilter,
  selectedIds,
  onFilterChange,
  onSelect,
  onRemove,
}: {
  items: WardrobeItem[];
  activeFilter: WardrobeFilter;
  selectedIds: Set<string>;
  onFilterChange: (filter: WardrobeFilter) => void;
  onSelect: (item: WardrobeItem) => void;
  onRemove: (item: WardrobeItem) => void;
}) {
  const { t } = useI18n();
  const filteredItems = activeFilter === "all" ? items : items.filter((item) => item.category === activeFilter);

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.dressingRoom.savedWardrobe}</p>
        </div>
        <WardrobeFilters activeFilter={activeFilter} onChange={onFilterChange} />
      </div>

      {items.length === 0 ? (
        <div className="border border-border bg-card p-6">
          <h2 className="font-serif text-3xl">{t.dressingRoom.emptyWardrobeTitle}</h2>
          <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{t.dressingRoom.emptyWardrobeDescription}</p>
          <Link href="/stylist" className="mt-5 inline-flex border-b border-primary pb-1 text-sm font-medium text-foreground">
            {t.dressingRoom.exploreStylist}
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filteredItems.map((item) => (
            <WardrobeItemCard
              key={item.id}
              item={item}
              selected={selectedIds.has(item.id)}
              onSelect={onSelect}
              onRemove={onRemove}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function CurrentLook({
  outfit,
  onRemove,
  onClear,
}: {
  outfit: OutfitState;
  onRemove: (slot: OutfitSlot) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const hasItems = outfitSlots.some((slot) => outfit[slot]);

  return (
    <section className="border-t border-border pt-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.dressingRoom.currentLook}</h2>
        {hasItems && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1 border-b border-primary pb-1 text-sm font-medium text-foreground"
          >
            <Trash2 className="size-3.5" />
            {t.dressingRoom.clearLook}
          </button>
        )}
      </div>
      <div className="mt-4 space-y-2">
        {outfitSlots.map((slot) => {
          const item = outfit[slot];

          return (
            <div key={slot} className="flex min-h-11 items-center justify-between gap-3 border border-border bg-background px-3 py-2">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{t.dressingRoom.slots[slot]}</div>
                <div className="mt-1 text-sm text-foreground">{item?.name || t.dressingRoom.emptySlot}</div>
              </div>
              {item && (
                <button
                  type="button"
                  onClick={() => onRemove(slot)}
                  aria-label={`${t.dressingRoom.remove} ${item.name}`}
                  className="text-muted-foreground transition hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <Button variant="outline" className="mt-4 w-full" disabled={!hasItems}>
        {t.dressingRoom.saveLook}
      </Button>
    </section>
  );
}

function OutfitPreview({
  virtualYou,
  outfit,
  uploadError,
  isUploading,
  onUpload,
  onRemove,
  onClear,
}: {
  virtualYou: VirtualYouProfile | null;
  outfit: OutfitState;
  uploadError: string;
  isUploading: boolean;
  onUpload: (file: File) => void;
  onRemove: (slot: OutfitSlot) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const selectedPieces = outfitSlots.map((slot) => outfit[slot]).filter(Boolean) as WardrobeItem[];
  const hasVirtualYou = Boolean(virtualYou);
  const displayImage = virtualYou?.modelImageUrl || defaultVirtualYouImage;

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (file) {
      onUpload(file);
    }
  }

  return (
    <aside className="space-y-6 border-t border-border pt-6 lg:sticky lg:top-24 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.dressingRoom.virtualYou}</p>
        <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
        <Button type="button" variant="outline" size="sm" onClick={() => inputRef.current?.click()} disabled={isUploading}>
          {isUploading ? <RefreshCw className="size-4 animate-spin" /> : <Upload className="size-4" />}
          {isUploading ? t.dressingRoom.uploading : t.dressingRoom.uploadPhoto}
        </Button>
      </div>

      <div className="relative flex min-h-[520px] items-end justify-center overflow-hidden border border-border bg-card px-6 pt-10">
        <div className="absolute bottom-16 left-1/2 h-72 w-52 -translate-x-1/2 rounded-[50%] bg-primary/10 blur-3xl" />
        {hasVirtualYou ? (
          <div
            role="img"
            aria-label={t.dressingRoom.virtualYou}
            className="relative z-10 h-[470px] w-[86%] bg-contain bg-bottom bg-no-repeat"
            style={{ backgroundImage: `url(${displayImage})` }}
          />
        ) : (
          <div className="relative z-10 mb-14 max-w-xs text-center">
            <p className="font-serif text-3xl leading-tight">{t.dressingRoom.createVirtualYouTitle}</p>
            <Button type="button" className="mt-5" onClick={() => inputRef.current?.click()} disabled={isUploading}>
              <Plus className="size-4" />
              {isUploading ? t.dressingRoom.uploading : t.dressingRoom.uploadPhoto}
            </Button>
          </div>
        )}
      </div>

      {selectedPieces.length > 0 && (
        <p className="border-l border-primary pl-4 text-sm leading-6 text-muted-foreground">{t.dressingRoom.simulatedPreview}</p>
      )}
      {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}

      <CurrentLook outfit={outfit} onRemove={onRemove} onClear={onClear} />
    </aside>
  );
}

export function DressingRoomExperience() {
  const router = useRouter();
  const { t } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  const [savedWardrobeItems, setSavedWardrobeItems] = useState<WardrobeItem[]>([]);
  const [virtualYou, setVirtualYou] = useState<VirtualYouProfile | null>(null);
  const [activeFilter, setActiveFilter] = useState<WardrobeFilter>("all");
  const [outfit, setOutfit] = useState<OutfitState>({});
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const virtualYouObjectUrlRef = useRef<string | null>(null);

  const replaceVirtualYou = useCallback((nextProfile: VirtualYouProfile | null) => {
    const previousObjectUrl = virtualYouObjectUrlRef.current;
    const nextObjectUrl = nextProfile?.modelImageUrl.startsWith("blob:") ? nextProfile.modelImageUrl : null;

    if (previousObjectUrl && previousObjectUrl !== nextObjectUrl) {
      URL.revokeObjectURL(previousObjectUrl);
    }

    virtualYouObjectUrlRef.current = nextObjectUrl;
    setVirtualYou(nextProfile);
  }, []);

  const refresh = useCallback(async () => {
    const session = authService.getSession();

    if (!session) {
      router.replace("/login");
      return;
    }

    conversationService.ensureSeeded(session.id);
    setUser(session);
    setSavedWardrobeItems(preferenceService.listSavedItems(session.id));
    replaceVirtualYou(await virtualYouService.get(session.id));
  }, [replaceVirtualYou, router]);

  useEffect(() => {
    queueMicrotask(() => {
      void refresh();
    });

    window.addEventListener("intentweave-conversations-change", refresh);
    window.addEventListener(preferenceService.changeEvent, refresh);
    window.addEventListener("intentweave-virtual-you-change", refresh);

    return () => {
      window.removeEventListener("intentweave-conversations-change", refresh);
      window.removeEventListener(preferenceService.changeEvent, refresh);
      window.removeEventListener("intentweave-virtual-you-change", refresh);

      if (virtualYouObjectUrlRef.current) {
        URL.revokeObjectURL(virtualYouObjectUrlRef.current);
      }
    };
  }, [refresh]);

  const savedItems = useMemo(() => getSavedWardrobeItems(savedWardrobeItems), [savedWardrobeItems]);
  const selectedIds = useMemo(() => new Set(outfitSlots.map((slot) => outfit[slot]?.id).filter(Boolean) as string[]), [outfit]);

  async function handleUpload(file: File) {
    if (!user) {
      return;
    }

    setIsUploading(true);
    setUploadError("");

    try {
      const { extractedPersonImage } = await virtualYouService.extractPerson(file);
      replaceVirtualYou(
        await virtualYouService.saveExtractedPerson({
          userId: user.id,
          originalUserImage: file,
          extractedPersonImage,
          personBoundingBox: await getImageBounds(extractedPersonImage),
        }),
      );
    } catch (error) {
      console.error("[DressingRoom] Virtual You upload failed", error);
      setUploadError(t.dressingRoom.uploadError);
    } finally {
      setIsUploading(false);
    }
  }

  function removeSlot(slot: OutfitSlot) {
    setOutfit((current) => {
      const next = { ...current };
      delete next[slot];
      return next;
    });
  }

  function removeSavedItem(item: WardrobeItem) {
    if (!user) {
      return;
    }

    preferenceService.removeSavedItem(user.id, item.id);
    setOutfit((current) => {
      const next = { ...current };

      outfitSlots.forEach((slot) => {
        if (next[slot]?.id === item.id) {
          delete next[slot];
        }
      });

      return next;
    });
  }

  return (
    <div className="space-y-10">
      <section className="border-b border-border pb-8">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.dressingRoom.eyebrow}</p>
        <h1 className="mt-3 max-w-3xl font-serif text-5xl leading-none tracking-tight sm:text-6xl">
          {t.dressingRoom.title}
        </h1>
      </section>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_390px]">
        <div className="order-2 lg:order-1">
          <SavedWardrobe
            items={savedItems}
            activeFilter={activeFilter}
            selectedIds={selectedIds}
            onFilterChange={setActiveFilter}
            onSelect={(item) => setOutfit((current) => applyWardrobeItem(current, item))}
            onRemove={removeSavedItem}
          />
        </div>
        <div className="order-1 lg:order-2">
          <OutfitPreview
            virtualYou={virtualYou}
            outfit={outfit}
            uploadError={uploadError}
            isUploading={isUploading}
            onUpload={handleUpload}
            onRemove={removeSlot}
            onClear={() => setOutfit({})}
          />
        </div>
      </div>
    </div>
  );
}
