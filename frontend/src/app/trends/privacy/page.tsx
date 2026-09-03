import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PrivacyContent, { PRIVACY_METADATA } from "@/components/legal/PrivacyContent";
import { isStaticExport } from "@/lib/renderMode";

/**
 * /trends/privacy — the static export's address of /privacy (lib/sitePaths.ts:
 * the publisher never writes the webroot, so the root route is unreachable
 * on the live site). Same content component; outside the export this route
 * is a 404 so the workstation has one URL per page.
 */
export const metadata: Metadata = {
  ...PRIVACY_METADATA,
  alternates: { canonical: "/trends/privacy" },
};

export default function TrendsPrivacyPage() {
  if (!isStaticExport()) notFound();
  return <PrivacyContent />;
}
