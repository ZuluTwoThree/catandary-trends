import type { Metadata } from "next";

// The newsletter page itself is a client component, so its metadata lives in
// this segment layout.
export const metadata: Metadata = {
  title: "Weekly Trend Briefing — Catandary Trends",
  description:
    "The week's most important trend signals across eight industries — analyzed, contextualized, and delivered every Monday. Free, one email a week.",
};

export default function NewsletterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
