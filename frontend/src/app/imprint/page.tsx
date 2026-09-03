import type { Metadata } from "next";
import ImprintContent, { IMPRINT_METADATA } from "@/components/legal/ImprintContent";

export const metadata: Metadata = IMPRINT_METADATA;

export default function ImprintPage() {
  return <ImprintContent />;
}
