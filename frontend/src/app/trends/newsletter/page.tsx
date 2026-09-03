import type { Metadata } from "next";
import { isStaticExport } from "@/lib/renderMode";
import NewsletterClient from "@/components/newsletter/NewsletterClient";
import StaticBriefing from "@/components/newsletter/StaticBriefing";
import { loadPublicEdition, publicEditionIndex } from "@/lib/newsletterExport";

/**
 * /trends/newsletter
 *
 * Workstation instance: the client page (components/newsletter/
 * NewsletterClient.tsx) — /api/newsletter, week switcher, unchanged.
 *
 * Static export (Schritt E): rendered at build time — signup, the latest
 * edition, and the archive list of the last PUBLIC_NEWSLETTER_EDITIONS
 * briefings (lib/archiveWindow.ts), each a page of its own under
 * /trends/newsletter/<year>-w<week>. No fetch to /api/*; the signup posts
 * to the PHP double-opt-in backend. Article links inside the edition are
 * resolved against the article window (lib/newsletterEditions.ts).
 */
export async function generateMetadata(): Promise<Metadata> {
  if (!isStaticExport()) return {};
  return { alternates: { canonical: "/trends/newsletter" } };
}

export default async function NewsletterPage() {
  if (!isStaticExport()) return <NewsletterClient />;

  const editions = await publicEditionIndex();
  const latest = editions[0] ? await loadPublicEdition(editions[0].year, editions[0].week) : null;
  return <StaticBriefing edition={latest} editions={editions} variant="index" />;
}
