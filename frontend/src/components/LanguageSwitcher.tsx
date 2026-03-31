"use client";

import { useLocale } from "@/lib/locale-context";

export default function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();

  return (
    <div className="flex items-center rounded-md border border-border text-sm overflow-hidden">
      <button
        onClick={() => setLocale("de")}
        className={`px-2 py-1 transition-colors ${
          locale === "de"
            ? "bg-accent text-background font-medium"
            : "text-muted hover:text-foreground"
        }`}
      >
        DE
      </button>
      <button
        onClick={() => setLocale("en")}
        className={`px-2 py-1 transition-colors ${
          locale === "en"
            ? "bg-accent text-background font-medium"
            : "text-muted hover:text-foreground"
        }`}
      >
        EN
      </button>
    </div>
  );
}
