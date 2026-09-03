import type { Metadata } from "next";
import EnquiryContent, { ENQUIRY_METADATA } from "@/components/EnquiryContent";

export const metadata: Metadata = ENQUIRY_METADATA;

export default function EnquiryPage() {
  return <EnquiryContent />;
}
