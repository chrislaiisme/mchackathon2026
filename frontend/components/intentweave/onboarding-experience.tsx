"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authService } from "@/lib/services/auth";
import { onboardingService, type OnboardingProfile } from "@/lib/services/onboarding";
import { cn } from "@/lib/utils";

const AGE_OPTIONS = ["18-24", "25-34", "35-44", "45+"];
const GENDER_OPTIONS = ["Woman", "Man", "Non-binary", "Prefer not to say"];
const CONTEXT_OPTIONS = ["Work", "School", "Going out", "Dates", "Travel", "Active"];
const STYLE_OPTIONS = [
  { name: "Minimal", gradient: "from-stone-100 via-stone-200 to-zinc-100" },
  { name: "Casual", gradient: "from-sky-50 via-stone-100 to-indigo-100" },
  { name: "Streetwear", gradient: "from-zinc-200 via-neutral-100 to-violet-100" },
  { name: "Elegant", gradient: "from-[#f9f4ee] via-[#eee6df] to-[#f4edf8]" },
  { name: "Sporty", gradient: "from-[#eef5ee] via-[#f5f6f1] to-[#e9eef8]" },
  { name: "Romantic", gradient: "from-rose-50 via-[#f8f1f5] to-[#efe8f8]" },
  { name: "Vintage", gradient: "from-[#f3ede4] via-[#eee3d5] to-[#f8f5ef]" },
  { name: "Y2K", gradient: "from-[#edf5ff] via-[#f7efff] to-[#f5f7fb]" },
];

const initialProfile: OnboardingProfile = {
  ageRange: "",
  gender: "",
  styles: [],
  contexts: [],
};

function SelectionButton({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "h-11 border px-4 text-left text-sm transition focus-visible:border-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/20",
        selected
          ? "border-primary bg-accent text-foreground"
          : "border-border bg-card text-muted-foreground hover:border-foreground/35 hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

function StyleCard({
  name,
  gradient,
  selected,
  disabled,
  onClick,
}: {
  name: string;
  gradient: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "group overflow-hidden border bg-card text-left transition focus-visible:border-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-45",
        selected ? "border-primary" : "border-border hover:border-foreground/35",
      )}
    >
      <div className={cn("relative aspect-[4/5] bg-gradient-to-br", gradient)}>
        <div className="absolute inset-4 border border-white/60 bg-white/15" />
        <div className="absolute bottom-5 left-5 h-20 w-12 border border-white/70 bg-white/20" />
        <div className="absolute right-5 top-5 h-24 w-16 border border-foreground/10 bg-card/25" />
        <div className="absolute inset-0 bg-background/0 transition duration-500 group-hover:scale-[1.02]" />
        {selected && (
          <span className="absolute right-3 top-3 inline-flex size-7 items-center justify-center border border-primary bg-card text-primary">
            <Check className="size-4" />
          </span>
        )}
      </div>
      <div className="flex items-center justify-between p-4">
        <span className="font-serif text-xl leading-tight text-foreground">{name}</span>
        <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{selected ? "Selected" : "Mood"}</span>
      </div>
    </button>
  );
}

function OnboardingHeader({ step, onSkip }: { step: number; onSkip: () => void }) {
  return (
    <header className="border-b border-border/70 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex min-h-20 w-full max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <div className="flex items-center gap-3">
          <Image
            src="/brand/intentweave-app-icon.png"
            alt="IntentWeave logo"
            width={44}
            height={44}
            priority
            className="size-11 rounded-xl shadow-sm"
          />
          <div className="leading-tight">
            <div className="text-base font-semibold tracking-tight">IntentWeave</div>
            <div className="text-xs text-muted-foreground">Fashion memory</div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden w-32 bg-border sm:block">
            <div className="h-px bg-primary transition-all" style={{ width: `${(step / 3) * 100}%` }} />
          </div>
          <span className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
            {String(step).padStart(2, "0")} - 03
          </span>
          <button
            type="button"
            onClick={onSkip}
            className="inline-flex items-center gap-1 border-b border-transparent pb-1 text-sm text-muted-foreground transition hover:border-primary hover:text-foreground"
          >
            Skip
            <SkipForward className="size-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
}

function StepShell({
  label,
  title,
  copy,
  helper,
  children,
}: {
  label: string;
  title: React.ReactNode;
  copy: string;
  helper?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-10 lg:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.28fr)] lg:items-start">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{label}</p>
        <h1 className="mt-5 font-serif text-5xl leading-[1.02] tracking-tight text-foreground sm:text-6xl">{title}</h1>
        <p className="mt-6 max-w-md text-base leading-7 text-muted-foreground">{copy}</p>
        {helper && <p className="mt-5 text-xs uppercase tracking-[0.2em] text-primary">{helper}</p>}
      </div>
      <div>{children}</div>
    </section>
  );
}

function AboutYouStep({
  profile,
  setProfile,
}: {
  profile: OnboardingProfile;
  setProfile: (profile: OnboardingProfile) => void;
}) {
  return (
    <StepShell
      label="01 / About You"
      title={
        <>
          First, a little
          <br />
          about you.
        </>
      }
      copy="This gives your stylist a starting point for more relevant recommendations."
    >
      <div className="space-y-8">
        <div>
          <p className="mb-3 text-xs uppercase tracking-[0.22em] text-muted-foreground">Age</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {AGE_OPTIONS.map((ageRange) => (
              <SelectionButton
                key={ageRange}
                label={ageRange}
                selected={profile.ageRange === ageRange}
                onClick={() => setProfile({ ...profile, ageRange })}
              />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-3 text-xs uppercase tracking-[0.22em] text-muted-foreground">Gender</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {GENDER_OPTIONS.map((gender) => (
              <SelectionButton
                key={gender}
                label={gender}
                selected={profile.gender === gender}
                onClick={() => setProfile({ ...profile, gender })}
              />
            ))}
          </div>
        </div>
      </div>
    </StepShell>
  );
}

function StylePreferenceStep({
  profile,
  setProfile,
}: {
  profile: OnboardingProfile;
  setProfile: (profile: OnboardingProfile) => void;
}) {
  function toggleStyle(style: string) {
    const selected = profile.styles.includes(style);
    const styles = selected
      ? profile.styles.filter((item) => item !== style)
      : profile.styles.length < 4
        ? [...profile.styles, style]
        : profile.styles;

    setProfile({ ...profile, styles });
  }

  return (
    <StepShell
      label="02 / Your Style"
      title={
        <>
          What feels
          <br />
          like you?
        </>
      }
      copy="Choose a few directions you naturally gravitate toward. Don't overthink it."
      helper="Choose up to 4"
    >
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {STYLE_OPTIONS.map((style) => {
          const selected = profile.styles.includes(style.name);
          return (
            <StyleCard
              key={style.name}
              name={style.name}
              gradient={style.gradient}
              selected={selected}
              disabled={!selected && profile.styles.length >= 4}
              onClick={() => toggleStyle(style.name)}
            />
          );
        })}
      </div>
    </StepShell>
  );
}

function EverydayContextStep({
  profile,
  setProfile,
}: {
  profile: OnboardingProfile;
  setProfile: (profile: OnboardingProfile) => void;
}) {
  function toggleContext(context: string) {
    const contexts = profile.contexts.includes(context)
      ? profile.contexts.filter((item) => item !== context)
      : [...profile.contexts, context];

    setProfile({ ...profile, contexts });
  }

  return (
    <StepShell
      label="03 / Everyday Life"
      title={
        <>
          What does your
          <br />
          everyday life look like?
        </>
      }
      copy="Choose the moments you dress for most often."
    >
      <div className="space-y-8">
        <div className="grid gap-2 sm:grid-cols-2">
          {CONTEXT_OPTIONS.map((context) => (
            <SelectionButton
              key={context}
              label={context}
              selected={profile.contexts.includes(context)}
              onClick={() => toggleContext(context)}
            />
          ))}
        </div>
        <p className="max-w-lg font-serif text-2xl leading-9 text-foreground">
          This is only a starting point.
          <br />
          <span className="text-muted-foreground">
            Your style will continue to evolve as you talk, try on, like and dislike looks.
          </span>
        </p>
      </div>
    </StepShell>
  );
}

function OnboardingNavigation({
  step,
  canContinue,
  onBack,
  onNext,
}: {
  step: number;
  canContinue: boolean;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div className="mt-10 flex items-center justify-between border-t border-border pt-5">
      <Button type="button" variant="outline" size="lg" onClick={onBack} disabled={step === 1}>
        <ArrowLeft className="size-4" />
        Back
      </Button>
      <Button type="button" size="lg" onClick={onNext} disabled={!canContinue}>
        {step === 3 ? "Start styling" : "Continue"}
        <ArrowRight className="size-4" />
      </Button>
    </div>
  );
}

function CompletionState({ profile }: { profile: OnboardingProfile }) {
  return (
    <section className="flex min-h-[62vh] items-center justify-center text-center">
      <div className="animate-[login-fade-up_700ms_ease_both]">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Your Style</p>
        <div className="mx-auto mt-6 flex max-w-xl flex-wrap justify-center gap-2">
          {[...profile.styles, ...profile.contexts].map((item) => (
            <span key={item} className="border border-border bg-card px-3 py-2 text-sm text-foreground">
              {item}
            </span>
          ))}
        </div>
        <h1 className="mt-8 font-serif text-5xl leading-tight text-foreground">
          A starting point,
          <br />
          not a label.
        </h1>
      </div>
    </section>
  );
}

export function OnboardingExperience() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState<OnboardingProfile>(initialProfile);
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    if (!authService.getSession()) {
      router.replace("/login");
      return;
    }

    if (onboardingService.isCompleted()) {
      router.replace("/stylist");
    }
  }, [router]);

  const canContinue = useMemo(() => {
    if (step === 1) {
      return Boolean(profile.ageRange && profile.gender);
    }

    if (step === 2) {
      return profile.styles.length > 0;
    }

    return profile.contexts.length > 0;
  }, [profile, step]);

  function finish(nextProfile = profile) {
    onboardingService.saveOnboardingProfile(nextProfile);
    setComplete(true);
    window.setTimeout(() => router.replace("/stylist"), 1200);
  }

  function skip() {
    const fallbackProfile: OnboardingProfile = {
      ageRange: profile.ageRange || "Prefer not to say",
      gender: profile.gender || "Prefer not to say",
      styles: profile.styles.length ? profile.styles : ["Minimal", "Casual"],
      contexts: profile.contexts.length ? profile.contexts : ["Work"],
    };
    setProfile(fallbackProfile);
    finish(fallbackProfile);
  }

  function next() {
    if (!canContinue) {
      return;
    }

    if (step < 3) {
      setStep((current) => current + 1);
      return;
    }

    finish();
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <OnboardingHeader step={step} onSkip={skip} />
      <main className="mx-auto w-full max-w-7xl px-5 py-10 sm:px-8 lg:py-14">
        {complete ? (
          <CompletionState profile={profile} />
        ) : (
          <>
            {step === 1 && <AboutYouStep profile={profile} setProfile={setProfile} />}
            {step === 2 && <StylePreferenceStep profile={profile} setProfile={setProfile} />}
            {step === 3 && <EverydayContextStep profile={profile} setProfile={setProfile} />}
            <OnboardingNavigation
              step={step}
              canContinue={canContinue}
              onBack={() => setStep((current) => Math.max(1, current - 1))}
              onNext={next}
            />
          </>
        )}
      </main>
    </div>
  );
}
