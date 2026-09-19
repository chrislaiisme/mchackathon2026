import type { User } from "@/lib/types";

// 2026-09-19：這支服務原本整段都是 localStorage mock（固定回傳一個 demoUser，
// 完全沒打過後端）。這次改成真的呼叫 ENGINE01 的 POST /auth/google，把 Google
// Identity Services 給的 credential 轉送給後端驗證，換回真正的 session_token／
// profile。本機快取（localStorage）還是留著，純粹是「這個瀏覽器分頁記得已經
// 登入」的機制，不是資料的真正來源。
const SESSION_KEY = "intentweave.session";

// 對齊後端 CLAUDE.md「CORS_ALLOWED_ORIGINS」的預設本機 port（ENGINE01 FastAPI）。
// 部署到別的網址時要在 frontend/.env.local 設 NEXT_PUBLIC_API_BASE_URL 覆蓋。
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// 後端 backend/shared/schemas.py 的 UserProfile／AuthResponse 形狀，
// 只列出這裡實際會用到的欄位。
interface BackendUserProfile {
  sub: string;
  email: string;
  name: string | null;
  picture: string | null;
  onboarding_completed: boolean;
}

interface BackendAuthResponse {
  session_token: string;
  profile: BackendUserProfile;
}

interface StoredSession {
  user: User;
  sessionToken: string;
}

function isBrowser() {
  return typeof window !== "undefined";
}

function toUser(profile: BackendUserProfile): User {
  // 後端欄位名稱（sub／picture）跟前端既有的 User 型別（id／avatarUrl）不一樣，
  // 在這裡做一次轉換，這樣其他已經在用 authService.getSession() 的元件
  // （app-shell、profile-experience、stylist-experience...）完全不用跟著改。
  return {
    id: profile.sub,
    name: profile.name || profile.email,
    email: profile.email,
    avatarUrl: profile.picture ?? "",
    onboardingCompleted: profile.onboarding_completed,
  };
}

function readStoredSession(): StoredSession | null {
  if (!isBrowser()) {
    return null;
  }

  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export const authService = {
  getSession(): User | null {
    return readStoredSession()?.user ?? null;
  },

  // 之後每個要打 ENGINE01 API 的呼叫都要帶 Authorization: Bearer <token>，
  // 這個 token 就是這裡存下來的 session_token（不是 Google 的 ID token）。
  getSessionToken(): string | null {
    return readStoredSession()?.sessionToken ?? null;
  },

  // idToken 是 Google Identity Services 登入成功後拿到的已簽章 credential，
  // 原封不動轉送給後端驗證——前端不用、也不應該自己驗證這個 token。
  async signInWithGoogle(idToken: string): Promise<User> {
    const response = await fetch(`${API_BASE_URL}/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });

    if (!response.ok) {
      throw new Error(`後端登入驗證失敗（HTTP ${response.status}）`);
    }

    const data = (await response.json()) as BackendAuthResponse;
    const user = toUser(data.profile);
    const session: StoredSession = { user, sessionToken: data.session_token };

    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    window.dispatchEvent(new Event("intentweave-auth-change"));
    return user;
  },

  signOut() {
    window.localStorage.removeItem(SESSION_KEY);
    window.dispatchEvent(new Event("intentweave-auth-change"));
  },
};
