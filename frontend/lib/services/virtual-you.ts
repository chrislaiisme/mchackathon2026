import type { FashionRecommendation, VirtualYouMeasurements, VirtualYouProfile } from "@/lib/types";

const VIRTUAL_YOU_KEY = "intentweave.virtualYou";
const VIRTUAL_YOU_DB = "intentweave.virtualYou.photos";
const VIRTUAL_YOU_PHOTO_STORE = "photos";
const VIRTUAL_YOU_DB_VERSION = 1;

export const defaultVirtualYouImage =
  "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=900&q=80";

interface StoredVirtualYouProfile {
  userId: string;
  hasCustomPhoto: boolean;
  hasExtractedPerson: boolean;
  hasCurrentTryOn?: boolean;
  selectedDefaultModelUrl?: string;
  isDefaultModel: boolean;
  measurements: VirtualYouMeasurements;
  processingMode: "mock" | "generated";
  personBoundingBox?: VirtualYouProfile["personBoundingBox"];
  updatedAt: string;
}

type LegacyVirtualYouProfile = Partial<StoredVirtualYouProfile> & {
  modelImageUrl?: string;
  sourceImageUrl?: string;
};

function isBrowser() {
  return typeof window !== "undefined";
}

function isDataUrl(value: unknown): value is string {
  return typeof value === "string" && value.startsWith("data:");
}

function dataUrlToBlob(dataUrl: string) {
  const [header, data] = dataUrl.split(",");
  const mime = header.match(/data:([^;]+)/)?.[1] || "application/octet-stream";
  const binary = window.atob(data || "");
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return new Blob([bytes], { type: mime });
}

function toStoredProfile(userId: string, profile: LegacyVirtualYouProfile): StoredVirtualYouProfile {
  const hasLegacyCustomPhoto = isDataUrl(profile.modelImageUrl) || isDataUrl(profile.sourceImageUrl);
  const selectedDefaultModelUrl =
    profile.selectedDefaultModelUrl ||
    (profile.isDefaultModel && typeof profile.modelImageUrl === "string" && !isDataUrl(profile.modelImageUrl)
      ? profile.modelImageUrl
      : undefined);

  return {
    userId,
    hasCustomPhoto: Boolean(profile.hasCustomPhoto || hasLegacyCustomPhoto),
    hasExtractedPerson: Boolean(profile.hasExtractedPerson || profile.hasCustomPhoto || hasLegacyCustomPhoto),
    selectedDefaultModelUrl,
    isDefaultModel: Boolean(profile.isDefaultModel),
    measurements: profile.measurements || {},
    processingMode: profile.processingMode || "mock",
    personBoundingBox: profile.personBoundingBox,
    updatedAt: profile.updatedAt || new Date().toISOString(),
  };
}

function readRawProfiles(): Record<string, LegacyVirtualYouProfile> {
  if (!isBrowser()) {
    return {};
  }

  const raw = window.localStorage.getItem(VIRTUAL_YOU_KEY);

  if (!raw) {
    return {};
  }

  try {
    return JSON.parse(raw) as Record<string, LegacyVirtualYouProfile>;
  } catch {
    window.localStorage.removeItem(VIRTUAL_YOU_KEY);
    return {};
  }
}

function writeMetadata(profiles: Record<string, StoredVirtualYouProfile>) {
  window.localStorage.setItem(VIRTUAL_YOU_KEY, JSON.stringify(profiles));
  window.dispatchEvent(new Event("intentweave-virtual-you-change"));
}

function openPhotoDb() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    if (!isBrowser() || !("indexedDB" in window)) {
      reject(new Error("IndexedDB is not available in this browser."));
      return;
    }

    const request = window.indexedDB.open(VIRTUAL_YOU_DB, VIRTUAL_YOU_DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;

      if (!db.objectStoreNames.contains(VIRTUAL_YOU_PHOTO_STORE)) {
        db.createObjectStore(VIRTUAL_YOU_PHOTO_STORE);
      }
    };
    request.onerror = () => reject(request.error || new Error("Unable to open IndexedDB."));
    request.onsuccess = () => resolve(request.result);
  });
}

async function withPhotoStore<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>) {
  const db = await openPhotoDb();

  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(VIRTUAL_YOU_PHOTO_STORE, mode);
    const store = transaction.objectStore(VIRTUAL_YOU_PHOTO_STORE);
    const request = action(store);

    request.onerror = () => reject(request.error || new Error("Unable to access Virtual You photo storage."));
    request.onsuccess = () => resolve(request.result);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => {
      db.close();
      reject(transaction.error || new Error("Unable to access Virtual You photo storage."));
    };
  });
}

function originalPhotoKey(userId: string) {
  return `${userId}:original`;
}

function extractedPersonKey(userId: string) {
  return `${userId}:extracted-person`;
}

function currentTryOnKey(userId: string) {
  return `${userId}:current-try-on`;
}

async function putPhoto(key: string, photo: Blob) {
  await withPhotoStore("readwrite", (store) => store.put(photo, key));
}

async function getPhoto(key: string) {
  return withPhotoStore<Blob | undefined>("readonly", (store) => store.get(key));
}

async function deletePhoto(key: string) {
  await withPhotoStore("readwrite", (store) => store.delete(key));
}

async function deleteVirtualYouPhotos(userId: string) {
  await Promise.all([
    deletePhoto(userId),
    deletePhoto(originalPhotoKey(userId)),
    deletePhoto(extractedPersonKey(userId)),
    deletePhoto(currentTryOnKey(userId)),
  ]);
}

async function migrateLegacyProfiles() {
  const rawProfiles = readRawProfiles();
  const migrated: Record<string, StoredVirtualYouProfile> = {};
  let changed = false;

  await Promise.all(
    Object.entries(rawProfiles).map(async ([userId, profile]) => {
      const stored = toStoredProfile(userId, profile);
      const legacyPhoto = isDataUrl(profile.modelImageUrl)
        ? profile.modelImageUrl
        : isDataUrl(profile.sourceImageUrl)
          ? profile.sourceImageUrl
          : null;

      if (legacyPhoto) {
        changed = true;

        try {
          const legacyBlob = dataUrlToBlob(legacyPhoto);
          await putPhoto(originalPhotoKey(userId), legacyBlob);
          await putPhoto(extractedPersonKey(userId), legacyBlob);
          stored.hasCustomPhoto = true;
          stored.hasExtractedPerson = true;
          stored.isDefaultModel = false;
          stored.selectedDefaultModelUrl = undefined;
        } catch {
          stored.hasCustomPhoto = false;
          stored.hasExtractedPerson = false;
        }
      }

      if ("modelImageUrl" in profile || "sourceImageUrl" in profile) {
        changed = true;
      }

      migrated[userId] = stored;
    }),
  );

  if (changed) {
    writeMetadata(migrated);
  }

  return migrated;
}

async function readMetadata() {
  const migrated = await migrateLegacyProfiles();
  return Object.keys(migrated).length ? migrated : (readRawProfiles() as Record<string, StoredVirtualYouProfile>);
}

function toRuntimeProfile(profile: StoredVirtualYouProfile, modelImageUrl: string, storageError?: string): VirtualYouProfile {
  return {
    ...profile,
    modelImageUrl,
    storageError,
  };
}

export interface MockTryOnPreview {
  id: string;
  generatedImageUrl: string;
  virtualYouImageUrl: string;
  outfitImageUrl: string;
  outfitName: string;
  provider: "mock" | "remote";
}

export interface ExtractPersonResult {
  extractedPersonImage: Blob;
}

export interface TryOnResult {
  id: string;
  generatedImage: Blob;
  generatedImageUrl: string;
  virtualYouImageUrl: string;
  outfitImageUrl: string;
  outfitName: string;
  provider: "mock" | "remote";
}

export interface RunVirtualTryOnResult {
  generatedImage: Blob;
  generatedImageUrl: string;
  outfitName: string;
  provider: "mock" | "remote";
}

function base64ToBlob(base64: string, type: string) {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return new Blob([bytes], { type });
}

async function fetchImageBlob(url: string) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("image_fetch_failed");
  }

  return response.blob();
}

function tryOnCategory(item: FashionRecommendation) {
  if (item.itemType === "bottom") {
    return "lower_body";
  }

  if (item.itemType === "dress") {
    return "dress";
  }

  return "upper_body";
}

export const virtualYouService = {
  async get(userId: string) {
    const profile = (await readMetadata())[userId];

    if (!profile) {
      return null;
    }

    if (!profile.hasExtractedPerson) {
      return toRuntimeProfile(profile, profile.selectedDefaultModelUrl || defaultVirtualYouImage);
    }

    try {
      const photo =
        (profile.hasCurrentTryOn ? await getPhoto(currentTryOnKey(userId)) : undefined) ||
        (await getPhoto(extractedPersonKey(userId))) ||
        (await getPhoto(userId));

      if (!photo) {
        return toRuntimeProfile(profile, defaultVirtualYouImage, "Your saved Virtual You photo could not be found.");
      }

      return toRuntimeProfile(profile, URL.createObjectURL(photo));
    } catch {
      return toRuntimeProfile(profile, defaultVirtualYouImage, "Your saved Virtual You photo could not be loaded.");
    }
  },

  createMockVirtualYou(photo: Blob) {
    return {
      photo,
      provider: "mock" as const,
      notes: [
        "Preserve identity and facial cues",
        "Preserve body proportions",
        "Apply light photoreal editorial styling",
      ],
    };
  },

  async save(userId: string, photo: Blob | null, measurements: VirtualYouMeasurements) {
    const existing = (await readMetadata())[userId];
    const profiles = await readMetadata();
    const processed = photo ? this.createMockVirtualYou(photo) : null;

    if (processed) {
      await putPhoto(originalPhotoKey(userId), processed.photo);
      await putPhoto(extractedPersonKey(userId), processed.photo);
    }

    const next: StoredVirtualYouProfile = {
      userId,
      hasCustomPhoto: Boolean(photo || existing?.hasCustomPhoto),
      hasExtractedPerson: Boolean(photo || existing?.hasExtractedPerson),
      hasCurrentTryOn: false,
      isDefaultModel: false,
      measurements,
      processingMode: processed?.provider || existing?.processingMode || "mock",
      personBoundingBox: existing?.personBoundingBox,
      updatedAt: new Date().toISOString(),
    };

    writeMetadata({ ...profiles, [userId]: next });
    return this.get(userId);
  },

  async saveExtractedPerson({
    userId,
    originalUserImage,
    extractedPersonImage,
    personBoundingBox,
  }: {
    userId: string;
    originalUserImage: Blob;
    extractedPersonImage: Blob;
    personBoundingBox: NonNullable<VirtualYouProfile["personBoundingBox"]>;
  }) {
    console.log("[CreateYou] Persisting extracted person asset", {
      originalUserImageSize: originalUserImage.size,
      extractedPersonImageSize: extractedPersonImage.size,
      personBoundingBox,
    });

    const profiles = await readMetadata();

    await putPhoto(originalPhotoKey(userId), originalUserImage);
    await putPhoto(extractedPersonKey(userId), extractedPersonImage);
    await deletePhoto(currentTryOnKey(userId)).catch(() => undefined);

    const next: StoredVirtualYouProfile = {
      userId,
      hasCustomPhoto: true,
      hasExtractedPerson: true,
      hasCurrentTryOn: false,
      isDefaultModel: false,
      measurements: profiles[userId]?.measurements || {},
      processingMode: "generated",
      personBoundingBox,
      updatedAt: new Date().toISOString(),
    };

    writeMetadata({ ...profiles, [userId]: next });
    console.log("[CreateYou] Extracted person asset saved");
    return this.get(userId);
  },

  async useDefault(userId: string) {
    const profiles = await readMetadata();
    await deleteVirtualYouPhotos(userId);

    const next: StoredVirtualYouProfile = {
      userId,
      hasCustomPhoto: false,
      hasExtractedPerson: false,
      hasCurrentTryOn: false,
      selectedDefaultModelUrl: defaultVirtualYouImage,
      isDefaultModel: true,
      measurements: {},
      processingMode: "mock",
      updatedAt: new Date().toISOString(),
    };

    writeMetadata({ ...profiles, [userId]: next });
    return this.get(userId);
  },

  async reset(userId: string) {
    const profiles = await readMetadata();
    delete profiles[userId];
    await deleteVirtualYouPhotos(userId);
    writeMetadata(profiles);
  },

  async extractPerson(originalUserImage: Blob, filename = "create-you-source.jpg"): Promise<ExtractPersonResult> {
    const formData = new FormData();
    formData.append("image", originalUserImage, filename);

    const response = await fetch("/api/virtual-you/extract", {
      method: "POST",
      body: formData,
    });
    const responseText = await response.text().catch(() => "");
    let result: { imageBase64?: string; error?: string; details?: unknown } | null = null;

    if (responseText) {
      try {
        result = JSON.parse(responseText) as { imageBase64?: string; error?: string; details?: unknown };
      } catch {
        result = null;
      }
    }

    if (!response.ok || !result?.imageBase64) {
      const debugPayload = {
        status: response.status,
        statusText: response.statusText,
        error: result?.error,
        details: result?.details,
        body: responseText.slice(0, 1200),
      };
      const detailSummary =
        typeof result?.details === "object" && result.details !== null
          ? JSON.stringify(result.details).slice(0, 600)
          : responseText.slice(0, 600);
      const error = new Error(result?.error || `background_removal_failed_${response.status}: ${detailSummary}`);
      (error as Error & { details?: unknown }).details = result?.details;
      console.error("[CreateYou] Extraction API returned no image", JSON.stringify(debugPayload, null, 2));
      throw error;
    }

    return {
      extractedPersonImage: base64ToBlob(result.imageBase64, "image/png"),
    };
  },

  async saveCurrentTryOn({
    userId,
    currentTryOnImage,
    personBoundingBox,
  }: {
    userId: string;
    currentTryOnImage: Blob;
    personBoundingBox: NonNullable<VirtualYouProfile["personBoundingBox"]>;
  }) {
    const profiles = await readMetadata();
    const existing = profiles[userId];

    if (!existing) {
      throw new Error("virtual_you_profile_missing");
    }

    await putPhoto(currentTryOnKey(userId), currentTryOnImage);

    const next: StoredVirtualYouProfile = {
      ...existing,
      hasCurrentTryOn: true,
      personBoundingBox,
      updatedAt: new Date().toISOString(),
    };

    writeMetadata({ ...profiles, [userId]: next });
    return this.get(userId);
  },

  async getTryOnSourceImage(profile: VirtualYouProfile | null) {
    const virtualYouImageUrl = profile?.modelImageUrl || defaultVirtualYouImage;

    if (profile?.hasExtractedPerson) {
      const personImage = (await getPhoto(extractedPersonKey(profile.userId))) || (await getPhoto(profile.userId));

      if (!personImage) {
        throw new Error("virtual_you_source_missing");
      }

      return personImage;
    }

    return fetchImageBlob(virtualYouImageUrl);
  },

  async generateVirtualTryOnFromPerson(
    personImage: Blob,
    outfit: FashionRecommendation,
    virtualYouImageUrl = defaultVirtualYouImage,
  ): Promise<TryOnResult> {
    const garmentImage = await fetchImageBlob(outfit.imageUrl).catch(() => null);
    const formData = new FormData();

    formData.append("personImage", personImage, "virtual-you.png");
    formData.append("garmentImageUrl", outfit.imageUrl);

    if (garmentImage) {
      formData.append("garmentImage", garmentImage, "garment.jpg");
    }

    formData.append("category", tryOnCategory(outfit));
    formData.append("garmentId", outfit.id);
    formData.append("garmentName", outfit.name);

    const response = await fetch("/api/virtual-you/try-on", {
      method: "POST",
      body: formData,
    });
    const result = (await response.json().catch(() => null)) as
      | { imageBase64?: string; provider?: "mock" | "remote"; error?: string }
      | null;

    if (!response.ok || !result?.imageBase64) {
      throw new Error(result?.error || "try_on_failed");
    }

    if (result.provider === "mock") {
      throw new Error("try_on_provider_mock");
    }

    const generatedImage = base64ToBlob(result.imageBase64, "image/png");
    const generatedImageUrl = URL.createObjectURL(generatedImage);

    return {
      id: `${result.provider || "remote"}-try-on-${Date.now()}`,
      generatedImage,
      generatedImageUrl,
      virtualYouImageUrl,
      outfitImageUrl: outfit.imageUrl,
      outfitName: outfit.name,
      provider: result.provider || "remote",
    };
  },

  async generateVirtualTryOn(profile: VirtualYouProfile | null, outfit: FashionRecommendation): Promise<TryOnResult> {
    return this.generateVirtualTryOnFromPerson(
      await this.getTryOnSourceImage(profile),
      outfit,
      profile?.modelImageUrl || defaultVirtualYouImage,
    );
  },

  async runVirtualTryOn(profile: VirtualYouProfile | null, garments: FashionRecommendation[]): Promise<RunVirtualTryOnResult> {
    if (garments.length === 0) {
      throw new Error("try_on_no_garments");
    }

    let workingPersonImage = await this.getTryOnSourceImage(profile);
    let lastResult: TryOnResult | null = null;

    for (const garment of garments) {
      if (lastResult?.generatedImageUrl) {
        URL.revokeObjectURL(lastResult.generatedImageUrl);
      }

      lastResult = await this.generateVirtualTryOnFromPerson(
        workingPersonImage,
        garment,
        profile?.modelImageUrl || defaultVirtualYouImage,
      );
      workingPersonImage = lastResult.generatedImage;
    }

    if (!lastResult) {
      throw new Error("try_on_missing_result");
    }

    const { extractedPersonImage } = await this.extractPerson(workingPersonImage, "try-on-result.png");
    URL.revokeObjectURL(lastResult.generatedImageUrl);

    return {
      generatedImage: extractedPersonImage,
      generatedImageUrl: URL.createObjectURL(extractedPersonImage),
      outfitName: garments.map((garment) => garment.name).join(" + "),
      provider: lastResult.provider,
    };
  },

  generateMockVirtualTryOn(profile: VirtualYouProfile | null, outfit: FashionRecommendation): MockTryOnPreview {
    const virtualYouImageUrl = profile?.modelImageUrl || defaultVirtualYouImage;

    return {
      id: `mock-try-on-${Date.now()}`,
      generatedImageUrl: virtualYouImageUrl,
      virtualYouImageUrl,
      outfitImageUrl: outfit.imageUrl,
      outfitName: outfit.name,
      provider: "mock",
    };
  },
};
