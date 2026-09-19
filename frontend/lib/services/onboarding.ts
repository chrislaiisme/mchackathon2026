export interface OnboardingProfile {
  ageRange: string;
  gender: string;
  styles: string[];
  contexts: string[];
}

const ONBOARDING_COMPLETED_KEY = "intentweave.onboardingCompleted";
const STYLE_PROFILE_KEY = "intentweave.styleProfile";

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
    window.localStorage.setItem(STYLE_PROFILE_KEY, JSON.stringify(profile));
    window.localStorage.setItem(ONBOARDING_COMPLETED_KEY, "true");
    window.dispatchEvent(new Event("intentweave-onboarding-change"));
  },
};
