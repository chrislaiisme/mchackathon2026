"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown, LogOut, Settings, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/components/intentweave/i18n-provider";
import { authService } from "@/lib/services/auth";
import type { Locale } from "@/lib/i18n/dictionaries";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/stylist", key: "stylist" },
  { href: "/insights", key: "insights" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { locale, setLocale, t } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    function syncSession() {
      const nextUser = authService.getSession();
      setUser(nextUser);

      if (!nextUser && pathname !== "/login") {
        router.replace("/login");
      }
    }

    syncSession();
    window.addEventListener("intentweave-auth-change", syncSession);
    window.addEventListener("storage", syncSession);

    return () => {
      window.removeEventListener("intentweave-auth-change", syncSession);
      window.removeEventListener("storage", syncSession);
    };
  }, [pathname, router]);

  function signOut() {
    authService.signOut();
    setMenuOpen(false);
    router.replace("/login");
  }

  if (isLogin) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="min-h-screen bg-transparent text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/95 backdrop-blur-xl">
        <div className="mx-auto flex min-h-16 w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/stylist" className="flex items-center gap-3">
            <Image
              src="/brand/intentweave-app-icon.png"
              alt="IntentWeave logo"
              width={40}
              height={40}
              priority
              className="size-10 rounded-xl shadow-sm"
            />
            <div className="leading-tight">
              <div className="text-base font-semibold tracking-tight">IntentWeave</div>
              <div className="hidden text-xs text-muted-foreground sm:block">Fashion memory</div>
            </div>
          </Link>

          <nav className="order-3 flex w-full items-center gap-5 md:order-none md:w-auto md:gap-7">
            {navItems.map((item) => {
              const active = pathname === item.href;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "relative inline-flex h-10 items-center text-sm font-medium transition-colors",
                    active
                      ? "text-foreground after:absolute after:bottom-0 after:left-0 after:h-px after:w-full after:bg-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {item.key === "stylist" ? t.nav.stylist : t.nav.insights}
                </Link>
              );
            })}
          </nav>

          {user && (
            <div className="flex items-center gap-2">
              <select
                aria-label={t.nav.language}
                value={locale}
                onChange={(event) => setLocale(event.target.value as Locale)}
                className="h-9 rounded-md border border-border bg-transparent px-2 text-sm text-muted-foreground outline-none transition focus:border-primary"
              >
                <option value="en">EN</option>
                <option value="zh-TW">繁中</option>
              </select>

              <div className="relative">
              <Button
                variant="outline"
                size="lg"
                className="h-10 gap-2 border-transparent bg-transparent px-2 hover:bg-muted"
                onClick={() => setMenuOpen((current) => !current)}
                aria-expanded={menuOpen}
                aria-haspopup="menu"
              >
                <span
                  role="img"
                  aria-label={user.name}
                  className="size-7 rounded-full object-cover"
                  style={{
                    backgroundImage: `url(${user.avatarUrl})`,
                    backgroundPosition: "center",
                    backgroundSize: "cover",
                  }}
                />
                <span className="hidden max-w-28 truncate sm:inline">{user.name}</span>
                <ChevronDown className="size-4 text-muted-foreground" />
              </Button>

              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-56 rounded-lg border border-border bg-card p-2 shadow-lg"
                >
                  <div className="border-b border-border px-3 py-2">
                    <div className="text-sm font-medium">{user.name}</div>
                    <div className="truncate text-xs text-muted-foreground">{user.email}</div>
                  </div>
                  <Link
                    href="/profile"
                    onClick={() => setMenuOpen(false)}
                    className="mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    <UserCircle className="size-4" />
                    {t.nav.profile}
                  </Link>
                  <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
                    <Settings className="size-4" />
                    {t.nav.settings}
                  </button>
                  <button
                    onClick={signOut}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-rose-600 hover:bg-rose-50"
                  >
                    <LogOut className="size-4" />
                    {t.nav.signOut}
                  </button>
                </div>
              )}
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</main>
    </div>
  );
}
