import type { Metadata } from "next";
import { notFound } from "next/navigation";
import EnquiryContent, { ENQUIRY_METADATA } from "@/components/EnquiryContent";
import { isStaticExport } from "@/lib/renderMode";

/**
 * /trends/enquiry — the static export's address of /enquiry (lib/sitePaths.ts:
 * the publisher never writes the webroot, so the root route is unreachable
 * on the live site). Same content component; outside the export this route
 * is a 404 so the workstation has one URL per page.
 */
export const metadata: Metadata = {
  ...ENQUIRY_METADATA,
  alternates: { canonical: "/trends/enquiry" },
};

export default function TrendsEnquiryPage() {
  if (!isStaticExport()) notFound();
  return <EnquiryContent />;
}
