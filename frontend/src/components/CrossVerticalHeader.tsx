"use client";

import Link from "next/link";
import { useLocale } from "@/lib/locale-context";

export default function CrossVerticalHeader({ count }: { count: number }) {
  const { t } = useLocale();

  return (
    <>
      <nav className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link
          href="/trends"
          className="hover:text-foreground transition-colors"
        >
          {t("trends")}
        </Link>
        <span>/</span>
        <span className="text-foreground">{t("crossVerticalTitle")}</span>
      </nav>

      <div className="mb-10">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
          {t("crossVerticalTitle")}
        </h1>
        <p className="text-muted text-lg max-w-2xl">
          {t("crossVerticalSubtitle")}
        </p>
        <p className="text-sm text-muted mt-2">
          {count} {t("megaTrendTrends")}
        </p>
      </div>
    </>
  );
}
