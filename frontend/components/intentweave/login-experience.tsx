"use client";

import { useEffect, useRef, useState } from "react";
import Script from "next/script";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { authService, DEV_BYPASS_AUTH } from "@/lib/services/auth";
import { onboardingService } from "@/lib/services/onboarding";

// 必須跟後端 .env 的 GOOGLE_CLIENT_ID 是同一組值（後端驗證 ID token 的
// audience 要對得上），見 CLAUDE.md「Google OAuth Client ID」跟這個 repo
// 根目錄的 backend/engine01_intent/main.py。要在 frontend/.env.local 設定，
// 那個檔案不進 git（frontend/.gitignore 已經排除所有 .env*）。
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

// Google Identity Services 的 script 是全域掛在 window.google 上，不是 npm 套件，
// 這裡補一個最小的型別宣告，只列出實際會用到的兩個方法。
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: Record<string, unknown>
          ) => void;
        };
      };
    };
  }
}

export function LoginExperience() {
  const router = useRouter();
  const [cursor, setCursor] = useState({ x: 0, y: 0 });
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [gsiScriptReady, setGsiScriptReady] = useState(false);
  const buttonHostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (authService.getSession()) {
      const user = authService.getSession();
      router.replace(user && onboardingService.isCompleted(user.id) ? "/stylist" : "/onboarding");
    }
  }, [router]);

  // 2026-09-19 起改成真的 Google 登入：GIS 的 callback 拿到 credential
  // （已簽章的 JWT）之後，直接轉送給後端 POST /auth/google 驗證換 session_token，
  // 不是像原本那樣塞一個寫死的 demoUser 進 localStorage。
  useEffect(() => {
    if (!gsiScriptReady || !GOOGLE_CLIENT_ID || !buttonHostRef.current) {
      return;
    }

    async function handleCredential(response: { credential: string }) {
      setIsSigningIn(true);
      setAuthError(null);
      try {
        const user = await authService.signInWithGoogle(response.credential);
        router.replace(onboardingService.isCompleted(user.id) ? "/stylist" : "/onboarding");
      } catch (error) {
        console.error("[login] Google 登入後呼叫後端失敗：", error);
        setAuthError("登入失敗，請確認 ENGINE01 後端服務是否已啟動，或稍後再試一次。");
        setIsSigningIn(false);
      }
    }

    window.google?.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleCredential,
    });
    window.google?.accounts.id.renderButton(buttonHostRef.current, {
      theme: "outline",
      size: "large",
      shape: "pill",
      text: "continue_with",
    });
  }, [gsiScriptReady, router]);

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setCursor({
      x: (event.clientX - rect.left) / rect.width - 0.5,
      y: (event.clientY - rect.top) / rect.height - 0.5,
    });
  }

  return (
    <div
      className="login-stage relative isolate flex min-h-screen overflow-hidden bg-[#fbf9ff] text-foreground"
      onPointerMove={handlePointerMove}
    >
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onReady={() => setGsiScriptReady(true)}
      />

      <div className="ambient-layer" />
      <div
        className="ambient-orbit hidden md:block"
        style={{
          transform: `translate3d(${cursor.x * 18}px, ${cursor.y * 18}px, 0)`,
        }}
      />

      <div className="ribbon-field" aria-hidden="true">
        <div className="woven-ribbon ribbon-one" />
        <div className="woven-ribbon ribbon-two" />
        <div className="woven-ribbon ribbon-three" />
        <div className="woven-ribbon ribbon-four" />
      </div>

      <main className="relative z-10 mx-auto grid min-h-screen w-full max-w-7xl items-center gap-10 px-6 py-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(420px,1.1fr)] lg:px-10">
        <section className="login-copy max-w-2xl">
          <div className="mb-10 inline-flex items-center gap-3 rounded-lg border border-white/70 bg-white/55 px-4 py-3 shadow-sm backdrop-blur-xl">
            <Image
              src="/brand/intentweave-app-icon.png"
              alt="IntentWeave logo"
              width={56}
              height={56}
              priority
              className="size-14 rounded-2xl shadow-sm"
            />
            <div>
              <div className="text-lg font-semibold tracking-tight">IntentWeave</div>
              <div className="text-sm text-muted-foreground">AI fashion companion</div>
            </div>
          </div>

          <p className="login-step mb-4 inline-flex items-center gap-2 rounded-md bg-primary/10 px-3 py-2 text-sm font-medium text-primary">
            <Sparkles className="size-4" />
            Preferences woven into personal style
          </p>
          <h1 className="login-step max-w-3xl text-5xl font-semibold leading-[1.05] tracking-tight text-[#21152f] sm:text-6xl lg:text-7xl">
            Discover what you want to wear, before you know how to say it.
          </h1>
          <p className="login-step mt-6 max-w-xl text-lg leading-8 text-muted-foreground">
            Your AI fashion companion learns what feels like you - one conversation at a time.
          </p>

          <div className="login-step mt-10 flex flex-col gap-3">
            {GOOGLE_CLIENT_ID ? (
              <div ref={buttonHostRef} />
            ) : (
              <p className="max-w-sm text-sm text-destructive">
                尚未設定 NEXT_PUBLIC_GOOGLE_CLIENT_ID——請在 frontend/.env.local
                填入跟後端 .env 一致的 GOOGLE_CLIENT_ID（見 CLAUDE.md「Google
                OAuth Client ID」）。
              </p>
            )}
            {/* 還沒建 Google OAuth Client ID 之前，本機要進得去。後端 .env 的
                DEV_BYPASS_AUTH 跟這裡的 NEXT_PUBLIC_DEV_BYPASS_AUTH 要一起開，
                正式 demo 兩個都要關掉，這顆按鈕就會消失。 */}
            {DEV_BYPASS_AUTH && (
              <button
                type="button"
                onClick={() => {
                  authService.signInAsDevUser();
                  router.replace(onboardingService.isCompleted() ? "/stylist" : "/onboarding");
                }}
                className="max-w-sm rounded-md border border-dashed border-primary/50 bg-primary/5 px-4 py-3 text-sm font-medium text-primary transition hover:bg-primary/10"
              >
                以本機測試帳號進入（DEV_BYPASS_AUTH）
              </button>
            )}
            {isSigningIn && (
              <p className="text-xs text-muted-foreground">登入中，請稍候...</p>
            )}
            {authError && <p className="text-sm text-destructive">{authError}</p>}
            <p className="max-w-sm text-xs leading-5 text-muted-foreground">
              使用真實 Google 帳號登入——後端會驗證這個帳號並建立你的 IntentWeave
              個人檔案。
            </p>
          </div>
        </section>

        <section className="login-panel hidden min-h-[560px] items-center justify-center lg:flex">
          <div className="relative h-[560px] w-full">
            <div className="absolute left-8 top-20 w-72 rounded-lg border border-white/70 bg-white/45 p-5 shadow-xl shadow-primary/10 backdrop-blur-2xl">
              <div className="mb-5 text-xs font-medium uppercase tracking-[0.2em] text-primary">Signal Weave</div>
              {["Minimal tailoring", "Lavender palette", "Relaxed fit", "Soft utility"].map((item, index) => (
                <div key={item} className="mb-4">
                  <div className="mb-2 flex justify-between text-sm">
                    <span>{item}</span>
                    <span className="text-primary">+{18 - index * 3}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/70">
                    <div className="h-2 rounded-full bg-primary" style={{ width: `${82 - index * 9}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="absolute bottom-28 right-4 w-80 rounded-lg border border-white/70 bg-white/55 p-5 shadow-xl shadow-primary/10 backdrop-blur-2xl">
              <div className="text-sm font-semibold">AI stylist memory</div>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                Conversational choices, visual preferences, and feedback are gently translated into a living style
                profile.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
