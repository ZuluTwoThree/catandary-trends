"use client";

import { useLocale } from "@/lib/locale-context";

export default function TrendsEmpty({ vertical }: { vertical: string | null }) {
  const { t } = useLocale();

  return (
    <div className="text-center py-20">
      <p className="text-muted text-lg">
        {t("emptyTitle")}
        {vertical ? ` ${t("emptyIn")} ${vertical}` : ""}
      </p>
      <p className="text-muted text-sm mt-2">{t("emptySubtitle")}</p>
    </div>
  );
}
