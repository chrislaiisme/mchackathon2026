"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { getRecommendations } from "@/lib/mock/stylist";
import { authService } from "@/lib/services/auth";
import { conversationService } from "@/lib/services/conversations";
import type { Conversation, User } from "@/lib/types";

export function ProfileExperience() {
  const router = useRouter();
  const { locale, setLocale, t } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const refresh = useCallback(() => {
    const session = authService.getSession();

    if (!session) {
      router.replace("/login");
      return;
    }

    conversationService.ensureSeeded(session.id);
    setUser(session);
    setConversations(conversationService.list(session.id));
  }, [router]);

  useEffect(() => {
    queueMicrotask(refresh);
    window.addEventListener("intentweave-conversations-change", refresh);

    return () => window.removeEventListener("intentweave-conversations-change", refresh);
  }, [refresh]);

  const signals = conversations[0]?.preferenceSignals || [];
  const savedLooks = useMemo(() => {
    const likedIds = new Set(
      conversations.flatMap((conversation) =>
        Object.entries(conversation.recommendationFeedback)
          .filter(([, value]) => value === "like")
          .map(([id]) => id),
      ),
    );

    return getRecommendations(locale).filter((recommendation) => likedIds.has(recommendation.id));
  }, [conversations, locale]);

  function reopenConversation(id: string) {
    conversationService.setCurrentId(id);
    router.push("/stylist");
  }

  function signOut() {
    authService.signOut();
    router.replace("/login");
  }

  return (
    <div className="space-y-12">
      <section className="grid gap-8 border-b border-border pb-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">IntentWeave</p>
          <h1 className="mt-3 font-serif text-6xl leading-none tracking-tight">{t.profile.title}</h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-muted-foreground">{t.profile.subtitle}</p>
        </div>
        {user && (
          <div className="border border-border bg-card p-5">
            <div
              className="mb-4 size-20 rounded-full bg-muted"
              style={{ backgroundImage: `url(${user.avatarUrl})`, backgroundPosition: "center", backgroundSize: "cover" }}
            />
            <div className="text-lg font-medium">{user.name}</div>
            <div className="text-sm text-muted-foreground">{user.email}</div>
          </div>
        )}
      </section>

      <section className="grid gap-8 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div>
          <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.profile.styleDna}</h2>
          <div className="mt-5 flex flex-wrap gap-2">
            {signals.map((signal) => (
              <span key={signal.label} className="border border-border bg-card px-4 py-3 text-sm">
                {signal.label}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.profile.learned}</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {[t.profile.memory1, t.profile.memory2, t.profile.memory3, t.profile.memory4].map((memory) => (
              <p key={memory} className="border-l border-primary pl-4 font-serif text-2xl leading-9">
                {memory}
              </p>
            ))}
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.profile.savedLooks}</h2>
        {savedLooks.length > 0 ? (
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {savedLooks.map((look) => (
              <article key={look.id} className="border border-border bg-card">
                <div className="fashion-image aspect-[3/4]" style={{ backgroundImage: `url(${look.imageUrl})` }} />
                <div className="p-4">
                  <div className="font-serif text-xl">{look.name}</div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{look.explanation}</p>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-5 border border-border bg-card p-6 text-muted-foreground">{t.profile.noSaved}</p>
        )}
      </section>

      <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.profile.pastSessions}</h2>
          <div className="mt-5 divide-y divide-border border border-border bg-card">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                onClick={() => reopenConversation(conversation.id)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-muted/50"
              >
                <span className="font-serif text-xl">{conversation.title}</span>
                <span className="text-sm text-muted-foreground">{t.profile.reopen}</span>
              </button>
            ))}
          </div>
        </div>

        <aside className="border border-border bg-card p-5">
          <h2 className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{t.profile.accountSettings}</h2>
          <div className="mt-5 space-y-5">
            <label className="block">
              <span className="text-sm text-muted-foreground">{t.profile.languagePreference}</span>
              <select
                value={locale}
                onChange={(event) => setLocale(event.target.value as "en" | "zh-TW")}
                className="mt-2 h-10 w-full border border-border bg-background px-3 text-sm"
              >
                <option value="en">English</option>
                <option value="zh-TW">繁體中文</option>
              </select>
            </label>
            <div>
              <div className="text-sm text-muted-foreground">{t.profile.accountInformation}</div>
              <div className="mt-2 text-sm">{user?.email}</div>
            </div>
            <Button variant="outline" onClick={signOut} className="w-full">
              {t.nav.signOut}
            </Button>
          </div>
        </aside>
      </section>
    </div>
  );
}
