"use client";

import { useLocale } from "@/lib/locale-context";

export default function TrendsHero() {
  const { t } = useLocale();

  return (
    <div className="mb-8">
      <h1 className="text-3xl font-bold tracking-tight mb-2">
        {t("heroTitle")}
      </h1>
      <p className="text-muted text-lg max-w-2xl">{t("heroSubtitle")}</p>
    </div>
  );
}
