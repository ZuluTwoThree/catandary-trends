import type { Metadata } from "next";
import { IBM_Plex_Serif, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const plexSerif = IBM_Plex_Serif({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-plex-serif",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
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
