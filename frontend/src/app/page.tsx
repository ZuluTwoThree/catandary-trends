import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { isStaticExport } from "@/lib/renderMode";

/**
 * `/` der Owner-App: Weiterleitung auf den Feed.
 *
 * Bis 2026-09-05 lag hier eine zweite, gepflegte Marketing-Landing (543 Zeilen,
 * sechs Landing-Komponenten). Sie war eine Kopie der oeffentlichen Seite und
 * driftete weg: Countdown auf den 01.09. ("We are live", waehrend die echte
 * Seite den 01.10. zeigt) und sechs Links auf entfernte Routen
 * (/trends/pricing, /trends/foresight* im PUBLIC_MODE). Die einzige gepflegte
 * Landing ist `docs/launch/preview.html` auf catandary.de; der Export laedt
 * dieses `/` bewusst nicht hoch (ROOT_ALLOWLIST in publish_static_site.py).
 * Der Owner startet ohnehin im Feed.
 */
export const metadata: Metadata = {
  title: "Catandary Trends",
  robots: { index: false, follow: false },
};

export default function RootPage() {
  if (!isStaticExport()) redirect("/trends");
  // Statischer Export: kein Server-Redirect moeglich — minimale Seite mit
  // Meta-Refresh. Wird nicht veroeffentlicht, existiert nur der Vollstaendigkeit halber.
  return (
    <html lang="en">
      <head>
        <meta httpEquiv="refresh" content="0; url=/trends" />
        <meta name="robots" content="noindex, nofollow" />
      </head>
      <body style={{ background: "#0a0c0a", color: "#e8e8e3", fontFamily: "system-ui, sans-serif", padding: "3rem" }}>
        <a href="/trends" style={{ color: "#d4ff3a" }}>Continue to the trend feed →</a>
      </body>
    </html>
  );
}
