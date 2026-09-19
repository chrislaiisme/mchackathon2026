"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart, Info, Mic, RefreshCw, Send, Shirt, SlidersHorizontal, Square, ThumbsDown, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { createStylistReply } from "@/lib/mock/stylist";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import {
  defaultVirtualYouImage,
  virtualYouService,
} from "@/lib/services/virtual-you";
import type {
  ChatMessage,
  Conversation,
  FashionRecommendation,
  PreferenceSignal,
  VirtualYouMeasurements,
  VirtualYouProfile,
  VisualChoice,
} from "@/lib/types";

function RecommendationCard({
  item,
  onFeedback,
  onTryOn,
  feedback,
  isTryOnActive,
  isTryOnLoading,
}: {
  item: FashionRecommendation;
  onFeedback: (id: string, value: "like" | "dislike", itemName: string) => void;
  onTryOn: (item: FashionRecommendation) => void;
  feedback?: "like" | "dislike";
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
  onTryOn,
  feedback,
  activeTryOnItemId,
  tryOnStatus,
}: {
  message: ChatMessage;
  index: number;
  onChoice: (prompt: string) => void;
  onFeedback: (id: string, value: "like" | "dislike", itemName: string) => void;
  onTryOn: (item: FashionRecommendation) => void;
  feedback: Record<string, "like" | "dislike">;
  activeTryOnItemId: string | null;
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
            <RecommendationCard
              key={item.id}
              item={item}
              feedback={feedback[item.id]}
              onFeedback={onFeedback}
              onTryOn={onTryOn}
              isTryOnActive={activeTryOnItemId === item.id}
              isTryOnLoading={tryOnStatus === "generating"}
            />
          ))}
        </div>
      )}
    </section>
  );
}

interface CreateYouApiErrorDetails {
  openaiStatus?: number;
  openaiBody?: string;
  message?: string;
}

type TryOnStatus = "idle" | "generating" | "error";

interface TryOnItemFeedback {
  itemId: string;
  feedback: "like" | "dislike";
  timestamp: string;
}

class CreateYouError extends Error {
  details?: CreateYouApiErrorDetails;

  constructor(message: string, details?: CreateYouApiErrorDetails) {
    super(message);
    this.name = "CreateYouError";
    this.details = details;
  }
}

function getCreateYouErrorCode(error: unknown) {
  return error instanceof CreateYouError ? error.message : error instanceof Error ? error.message : "image_processing_failed";
}

function base64ToBlob(base64: string, type = "image/png") {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return new Blob([bytes], { type });
}

async function removeBackground(originalUserImage: File) {
  console.log("[CreateYou] Starting segmentation/background removal");
  const formData = new FormData();
  formData.append("image", originalUserImage, originalUserImage.name || "create-you-source.jpg");

  console.log("[CreateYou] Calling backend: /api/virtual-you/extract");
  const response = await fetch("/api/virtual-you/extract", {
    method: "POST",
    body: formData,
  });
  console.log("[CreateYou] Backend response status:", response.status);

  const result = (await response.json().catch((error) => {
    console.error("[CreateYou] Failed to parse backend response", error);
    return null;
  })) as { imageBase64?: string; error?: string; details?: CreateYouApiErrorDetails } | null;

  if (!response.ok || !result?.imageBase64) {
    console.error("[CreateYou] Backend extraction failed", result);
    throw new CreateYouError(result?.error || "background_removal_failed", result?.details);
  }

  const personMask = base64ToBlob(result.imageBase64, "image/png");
  console.log("[CreateYou] Segmentation result:", {
    type: personMask.type,
    size: personMask.size,
    imageBase64Length: result.imageBase64.length,
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
  tryOnOverlayImage,
  isTryingOn,
  loadingLabel,
}: {
  baseImage: string;
  displayImage: string;
  tryOnOverlayImage?: string;
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
        {tryOnOverlayImage && (
          <div
            className="pointer-events-none absolute left-1/2 top-[23%] h-[42%] w-[58%] -translate-x-1/2 bg-contain bg-center bg-no-repeat opacity-60 mix-blend-multiply"
            style={{ backgroundImage: `url(${tryOnOverlayImage})` }}
            aria-hidden="true"
          />
        )}
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
  activeTryOnOverlayImage,
  tryOnStatus,
  tryOnError,
  activeTryOnFeedback,
  onTryOnFeedback,
}: {
  profile: VirtualYouProfile | null;
  isProcessing: boolean;
  error: string;
  onUpload: (file: File) => void;
  activeTryOnImage: string | null;
  activeTryOnOverlayImage: string | null;
  tryOnStatus: "idle" | "generating" | "error";
  tryOnError: string;
  activeTryOnFeedback?: "like" | "dislike";
  onTryOnFeedback: (feedback: "like" | "dislike") => void;
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
          tryOnOverlayImage={activeTryOnOverlayImage || undefined}
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
      {activeTryOnImage && tryOnStatus !== "generating" && (
        <TryOnFeedbackControls selected={activeTryOnFeedback} onSelect={onTryOnFeedback} />
      )}
    </section>
  );
}

function StylePanel({
  signals,
  feedbackCount,
  virtualYou,
  createYouProcessing,
  createYouError,
  onCreateYouUpload,
  activeTryOnImage,
  activeTryOnOverlayImage,
  tryOnStatus,
  tryOnError,
  activeTryOnFeedback,
  onTryOnFeedback,
}: {
  signals: PreferenceSignal[];
  feedbackCount: number;
  virtualYou: VirtualYouProfile | null;
  createYouProcessing: boolean;
  createYouError: string;
  onCreateYouUpload: (file: File) => void;
  activeTryOnImage: string | null;
  activeTryOnOverlayImage: string | null;
  tryOnStatus: "idle" | "generating" | "error";
  tryOnError: string;
  activeTryOnFeedback?: "like" | "dislike";
  onTryOnFeedback: (feedback: "like" | "dislike") => void;
}) {
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
      <CreateYouSection
        profile={virtualYou}
        isProcessing={createYouProcessing}
        error={createYouError}
        onUpload={onCreateYouUpload}
        activeTryOnImage={activeTryOnImage}
        activeTryOnOverlayImage={activeTryOnOverlayImage}
        tryOnStatus={tryOnStatus}
        tryOnError={tryOnError}
        activeTryOnFeedback={activeTryOnFeedback}
        onTryOnFeedback={onTryOnFeedback}
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
  const [voiceState, setVoiceState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [voiceElapsedSeconds, setVoiceElapsedSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const [virtualYou, setVirtualYou] = useState<VirtualYouProfile | null>(null);
  const [virtualYouModalOpen, setVirtualYouModalOpen] = useState(false);
  const [virtualYouStorageError, setVirtualYouStorageError] = useState("");
  const [createYouProcessing, setCreateYouProcessing] = useState(false);
  const [createYouError, setCreateYouError] = useState("");
  const [activeTryOnItemId, setActiveTryOnItemId] = useState<string | null>(null);
  const [activeTryOnImage, setActiveTryOnImage] = useState<string | null>(null);
  const [activeTryOnOverlayImage, setActiveTryOnOverlayImage] = useState<string | null>(null);
  const [tryOnStatus, setTryOnStatus] = useState<TryOnStatus>("idle");
  const [tryOnError, setTryOnError] = useState("");
  const [itemFeedback, setItemFeedback] = useState<Record<string, TryOnItemFeedback>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<number | null>(null);
  const shouldFollowRef = useRef(true);
  const virtualYouObjectUrlRef = useRef<string | null>(null);

  const activeConversation = conversations.find((conversation) => conversation.id === activeId);

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

    setConversations(list);
    setActiveId(nextActiveId);
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

    return () => {
      window.removeEventListener("intentweave-conversations-change", handleChange);
      window.removeEventListener("intentweave-auth-change", handleChange);
      window.removeEventListener("intentweave-virtual-you-change", handleChange);

      if (virtualYouObjectUrlRef.current) {
        URL.revokeObjectURL(virtualYouObjectUrlRef.current);
      }
    };
  }, [refreshConversations]);

  useEffect(() => {
    if (shouldFollowRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [activeConversation?.messages.length, isGenerating, activeId]);

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
      const formData = new FormData();
      const extension = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
      formData.append("audio", audio, `intentweave-voice.${extension}`);

      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
      });
      const result = (await response.json().catch(() => null)) as { text?: string; error?: string } | null;

      if (!response.ok || !result?.text) {
        setVoiceError(result?.error === "missing_api_key" ? t.stylist.voiceConfigError : t.stylist.voiceTranscriptionError);
        return;
      }

      appendTranscription(result.text);
    } catch {
      setVoiceError(t.stylist.voiceTranscriptionError);
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
      setActiveTryOnItemId(null);
      setActiveTryOnImage(null);
      setActiveTryOnOverlayImage(null);
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
      } else if (code === "openai_request_failed" || code === "openai_response_missing_image") {
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

  async function handleTryOn(item: FashionRecommendation) {
    if (tryOnStatus === "generating") {
      return;
    }

    if (activeTryOnItemId === item.id) {
      setActiveTryOnItemId(null);
      setActiveTryOnImage(null);
      setActiveTryOnOverlayImage(null);
      setTryOnStatus("idle");
      setTryOnError("");
      return;
    }

    setTryOnStatus("generating");
    setTryOnError("");
    setActiveTryOnItemId(item.id);
    setActiveTryOnImage(null);
    setActiveTryOnOverlayImage(null);

    try {
      await new Promise((resolve) => window.setTimeout(resolve, 320));
      const preview = virtualYouService.generateVirtualTryOn(virtualYou, item);
      setActiveTryOnImage(preview.generatedImageUrl);
      setActiveTryOnOverlayImage(preview.outfitImageUrl);
      setTryOnStatus("idle");
    } catch {
      setActiveTryOnItemId(null);
      setActiveTryOnImage(null);
      setActiveTryOnOverlayImage(null);
      setTryOnStatus("error");
      setTryOnError(t.virtualYou.tryOnError);
    }
  }

  function handleTryOnFeedback(feedbackValue: "like" | "dislike") {
    if (!activeTryOnItemId) {
      return;
    }

    setItemFeedback((current) => ({
      ...current,
      [activeTryOnItemId]: {
        itemId: activeTryOnItemId,
        feedback: feedbackValue,
        timestamp: new Date().toISOString(),
      },
    }));
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
              onTryOn={handleTryOn}
              feedback={feedback}
              activeTryOnItemId={activeTryOnItemId}
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
        virtualYou={virtualYou}
        createYouProcessing={createYouProcessing}
        createYouError={createYouError}
        onCreateYouUpload={handleCreateYouUpload}
        activeTryOnImage={activeTryOnImage}
        activeTryOnOverlayImage={activeTryOnOverlayImage}
        tryOnStatus={tryOnStatus}
        tryOnError={tryOnError}
        activeTryOnFeedback={activeTryOnItemId ? itemFeedback[activeTryOnItemId]?.feedback : undefined}
        onTryOnFeedback={handleTryOnFeedback}
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
