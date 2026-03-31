"use client";

import { useLocale } from "@/lib/locale-context";

export default function ForesightCta({ compact }: { compact?: boolean }) {
  const { t } = useLocale();

  if (compact) {
    return (
      <div className="mt-12 rounded-xl border border-accent/20 bg-accent/5 p-6 text-center">
        <p className="text-sm text-muted mb-3">{t("foresightCta")}</p>
        <a
          href="https://catandary.de"
          className="inline-flex items-center gap-2 bg-accent text-background px-4 py-2 rounded-lg text-sm font-medium hover:bg-accent/90 transition-colors"
        >
          Catandary Foresight
        </a>
      </div>
    );
  }

  return (
    <div className="mt-16 rounded-xl border border-accent/20 bg-accent/5 p-8 text-center">
      <h2 className="text-xl font-semibold mb-2">{t("ctaTitle")}</h2>
      <p className="text-muted mb-4 max-w-lg mx-auto">{t("ctaText")}</p>
      <a
        href="https://catandary.de"
        className="inline-flex items-center gap-2 bg-accent text-background px-5 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors"
      >
        {t("ctaButton")}
      </a>
    </div>
  );
}
