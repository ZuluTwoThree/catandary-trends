import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

// IBM Plex lokal (seit 2026-10-07, Owner): next/font/google holte die Font-CSS bei JEDEM
// Build neu von Google. Am 07.10. erweiterte Google einen unicode-range (U+20C0 → U+20C4),
// die CSS-Datei bekam einen neuen Namen, und jede Seite des statischen Exports galt als
// geändert (28.206 Dateien statt ~2.600). Die Dateien in src/fonts/ sind dieselben
// Versionen, die Google ausliefert (Serif 2.6, Mono 2.3, Sans 3.201, SIL OFL 1.1), mit
// Googles Zeichenbereichen und OpenType-Features geschnitten — Rezept in src/fonts/README.md.
const plexSerif = localFont({
  src: [
    { path: "../fonts/IBMPlexSerif-Regular.woff2", weight: "400", style: "normal" },
    { path: "../fonts/IBMPlexSerif-Italic.woff2", weight: "400", style: "italic" },
    { path: "../fonts/IBMPlexSerif-Medium.woff2", weight: "500", style: "normal" },
    { path: "../fonts/IBMPlexSerif-MediumItalic.woff2", weight: "500", style: "italic" },
    { path: "../fonts/IBMPlexSerif-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "../fonts/IBMPlexSerif-SemiBoldItalic.woff2", weight: "600", style: "italic" },
  ],
  variable: "--font-plex-serif",
  display: "swap",
  fallback: ["Georgia", "serif"],
});

const plexMono = localFont({
  src: [
    { path: "../fonts/IBMPlexMono-Regular.woff2", weight: "400", style: "normal" },
    { path: "../fonts/IBMPlexMono-Medium.woff2", weight: "500", style: "normal" },
    { path: "../fonts/IBMPlexMono-SemiBold.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
  fallback: ["ui-monospace", "monospace"],
});

const plexSans = localFont({
  src: [
    { path: "../fonts/IBMPlexSans-Light.woff2", weight: "300", style: "normal" },
    { path: "../fonts/IBMPlexSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "../fonts/IBMPlexSans-Medium.woff2", weight: "500", style: "normal" },
    { path: "../fonts/IBMPlexSans-SemiBold.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-plex-sans",
  display: "swap",
  fallback: ["system-ui", "sans-serif"],
});

/**
 * Absolute base for canonical/OG URLs (`alternates.canonical`, the default
 * opengraph-image). Without it Next resolves them against
 * http://localhost:<port> — visible in every exported page (spike
 * 2026-09-02). PUBLIC_SITE_URL overrides for a staging host.
 */
const SITE_URL = process.env.PUBLIC_SITE_URL || "https://catandary.de";
// Pre-launch switch (see robots.ts): PUBLIC_NOINDEX=1 keeps crawlers out
// until the owner flips it for 2026-10-01.
const NOINDEX = process.env.PUBLIC_NOINDEX === "1";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  // Machine-readable text-and-data-mining reservation for every page (TDMRep,
  // W3C CG; §44b Abs. 3 UrhG) — owner decision 2026-09-03. Paired with the
  // TDM-Reservation header (.htaccess) and /.well-known/tdmrep.json (build).
  // "noai, noimageai" is the publisher convention our own fetcher honours too.
  other: {
    "tdm-reservation": "1",
    "tdm-policy": `${SITE_URL}/trends/tdm-policy`,
    robots: "noai, noimageai",
  },
  ...(NOINDEX ? { robots: { index: false, follow: false } } : {}),
  title: "Catandary Trends — Cross-Industry Trend Intelligence",
  description:
    "Curated trend signals from eight industry verticals. Powered by Catandary Foresight.",
  openGraph: {
    title: "Catandary Trends",
    description: "Cross-Industry Trend Intelligence",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`dark ${plexSerif.variable} ${plexMono.variable} ${plexSans.variable}`}
    >
      <body className="bg-background text-foreground min-h-screen antialiased">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Header />
        <main id="main" tabIndex={-1}>
          {children}
        </main>
        <Footer />
      </body>
    </html>
  );
}
