import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ImprintContent, { IMPRINT_METADATA } from "@/components/legal/ImprintContent";
import { isStaticExport } from "@/lib/renderMode";

/**
 * /trends/imprint — the static export's address of /imprint (lib/sitePaths.ts:
 * the publisher never writes the webroot, so the root route is unreachable
 * on the live site). Same content component; outside the export this route
 * is a 404 so the workstation has one URL per page.
 */
export const metadata: Metadata = {
  ...IMPRINT_METADATA,
  alternates: { canonical: "/trends/imprint" },
};

export default function TrendsImprintPage() {
  if (!isStaticExport()) notFound();
  return <ImprintContent />;
}
