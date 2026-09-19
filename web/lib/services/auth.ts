import type { User } from "@/lib/types";

const SESSION_KEY = "intentweave.mockSession";

export const demoUser: User = {
  id: "user_demo_001",
  name: "Demo User",
  email: "demo@example.com",
  avatarUrl:
    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=160&q=80",
};

function isBrowser() {
  return typeof window !== "undefined";
}

export const authService = {
  getSession(): User | null {
    if (!isBrowser()) {
      return null;
    }

    const raw = window.localStorage.getItem(SESSION_KEY);

    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw) as User;
    } catch {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
  },

  signInWithGoogle(): User {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(demoUser));
    window.dispatchEvent(new Event("intentweave-auth-change"));
    return demoUser;
  },

  signOut() {
    window.localStorage.removeItem(SESSION_KEY);
    window.dispatchEvent(new Event("intentweave-auth-change"));
  },
};
