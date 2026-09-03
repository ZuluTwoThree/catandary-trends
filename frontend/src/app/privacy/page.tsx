import type { Metadata } from "next";
import PrivacyContent, { PRIVACY_METADATA } from "@/components/legal/PrivacyContent";

export const metadata: Metadata = PRIVACY_METADATA;

export default function PrivacyPage() {
  return <PrivacyContent />;
}
