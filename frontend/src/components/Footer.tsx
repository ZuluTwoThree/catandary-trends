"use client";

import { useLocale } from "@/lib/locale-context";

export default function Footer() {
  const { t } = useLocale();

  return (
    <footer className="border-t border-border mt-20">
      <div className="mx-auto max-w-7xl px-4 py-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted">
        <p>
          &copy; {new Date().getFullYear()} Catandary. {t("footerRights")}
        </p>
        <div className="flex items-center gap-4">
          <span>
            {t("footerPowered")}{" "}
            <a
              href="https://catandary.de"
              className="text-accent hover:underline"
            >
              Catandary Foresight
            </a>
          </span>
        </div>
      </div>
    </footer>
  );
}
