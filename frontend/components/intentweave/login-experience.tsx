"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { ArrowRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authService } from "@/lib/services/auth";
import { onboardingService } from "@/lib/services/onboarding";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1c-.22-.66-.35-1.36-.35-2.1s.13-1.44.35-2.1V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l3.66-2.84z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06L5.84 9.9C6.71 7.3 9.14 5.38 12 5.38z"
      />
    </svg>
  );
}

export function LoginExperience() {
  const router = useRouter();
  const [cursor, setCursor] = useState({ x: 0, y: 0 });
  const [isSigningIn, setIsSigningIn] = useState(false);

  useEffect(() => {
    if (authService.getSession()) {
      router.replace(onboardingService.isCompleted() ? "/stylist" : "/onboarding");
    }
  }, [router]);

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setCursor({
      x: (event.clientX - rect.left) / rect.width - 0.5,
      y: (event.clientY - rect.top) / rect.height - 0.5,
    });
  }

  function signIn() {
    setIsSigningIn(true);
    window.setTimeout(() => {
      authService.signInWithGoogle();
      router.replace(onboardingService.isCompleted() ? "/stylist" : "/onboarding");
    }, 420);
  }

  return (
    <div
      className="login-stage relative isolate flex min-h-screen overflow-hidden bg-[#fbf9ff] text-foreground"
      onPointerMove={handlePointerMove}
    >
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

          <div className="login-step mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
            <Button
              size="lg"
              onClick={signIn}
              disabled={isSigningIn}
              className="h-12 gap-3 px-5 text-base shadow-lg shadow-primary/20"
            >
              <GoogleIcon />
              {isSigningIn ? "Creating demo session..." : "Continue with Google"}
              <ArrowRight className="size-4" />
            </Button>
            <p className="max-w-sm text-xs leading-5 text-muted-foreground">
              Demo authentication only. By continuing, you agree to use a local mock session for this prototype.
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
