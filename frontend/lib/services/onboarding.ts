import { authService } from "@/lib/services/auth";

export interface OnboardingProfile {
  ageRange: string;
  gender: string;
  styles: string[];
  contexts: string[];
}

const ONBOARDING_COMPLETED_KEY = "intentweave.onboardingCompleted";
const STYLE_PROFILE_KEY = "intentweave.styleProfile";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function isBrowser() {
  return typeof window !== "undefined";
}

export const onboardingService = {
  isCompleted() {
    if (!isBrowser()) {
      return false;
    }

    return window.localStorage.getItem(ONBOARDING_COMPLETED_KEY) === "true";
  },

  getProfile(): OnboardingProfile | null {
    if (!isBrowser()) {
      return null;
    }

    const raw = window.localStorage.getItem(STYLE_PROFILE_KEY);

    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw) as OnboardingProfile;
    } catch {
      window.localStorage.removeItem(STYLE_PROFILE_KEY);
      return null;
    }
  },

  saveOnboardingProfile(profile: OnboardingProfile) {
    // 本地狀態照舊立刻寫，畫面轉場不用等網路——這支呼叫在 onboarding-experience.tsx
    // 裡是同步呼叫，改成整個 await 後端會牽動比較多地方，時間有限先不動那層。
    window.localStorage.setItem(STYLE_PROFILE_KEY, JSON.stringify(profile));
    window.localStorage.setItem(ONBOARDING_COMPLETED_KEY, "true");
    window.dispatchEvent(new Event("intentweave-onboarding-change"));

    // 2026-09-19 起同步把資料寫回後端 PUT /profile（真正的資料落地位置，
    // data/users/<sub>.json）。這裡刻意不 await、失敗只印 log：後端沒開或
    // 網路斷線時，onboarding 畫面體驗維持原本 localStorage-only 的樣子，
    // 只是這次的偏好資料不會真的存進後端，之後接個人化訊號時會讀不到。
    const sessionToken = authService.getSessionToken();
    if (!sessionToken) {
      console.warn("[onboarding] 沒有 session token，略過 PUT /profile（只存在本機）。");
      return;
    }

    fetch(`${API_BASE_URL}/profile`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify({
        age_range: profile.ageRange,
        gender: profile.gender,
        style_preferences: profile.styles,
        contexts: profile.contexts,
        onboarding_completed: true,
      }),
    }).catch((error: unknown) => {
      console.error("[onboarding] PUT /profile 失敗，資料只留在本機：", error);
    });
  },
};
