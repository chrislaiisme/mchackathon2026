import type { Metadata } from "next";
import { AppShell } from "@/components/intentweave/app-shell";
import { I18nProvider } from "@/components/intentweave/i18n-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "IntentWeave",
  description: "AI fashion styling and enterprise preference intelligence.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col">
        <I18nProvider>
          <AppShell>{children}</AppShell>
        </I18nProvider>
      </body>
    </html>
  );
}
