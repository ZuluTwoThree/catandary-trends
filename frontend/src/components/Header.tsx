"use client";

import { useLocale } from "@/lib/locale-context";
import LanguageSwitcher from "./LanguageSwitcher";

export default function Header() {
  const { t } = useLocale();

  return (
    <header className="border-b border-border">
      <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
        <a href="/trends" className="flex items-center gap-2">
          <span className="text-xl font-bold tracking-tight">
            Catandary <span className="text-accent">Trends</span>
          </span>
        </a>
        <nav className="flex items-center gap-4 text-sm text-muted">
          <a
            href="/trends"
            className="hover:text-foreground transition-colors"
          >
            {t("trends")}
          </a>
          <a
            href="/trends/mega"
            className="hover:text-foreground transition-colors hidden sm:inline"
          >
            {t("megaTrends")}
          </a>
          <a
            href="/trends/cross-vertical"
            className="hover:text-foreground transition-colors hidden md:inline"
          >
            {t("crossIndustry")}
          </a>
          <a
            href="/trends/foresight"
            className="hover:text-foreground transition-colors hidden md:inline"
          >
            {t("foresightCockpit")}
          </a>
          <a
            href="https://catandary.de"
            className="hover:text-foreground transition-colors hidden sm:inline"
            target="_blank"
            rel="noopener noreferrer"
          >
            Catandary
          </a>
          <a
            href="/trends/newsletter"
            className="bg-accent/10 text-accent px-3 py-1.5 rounded-md hover:bg-accent/20 transition-colors"
          >
            {t("newsletter")}
          </a>
          <LanguageSwitcher />
        </nav>
      </div>
    </header>
  );
}
