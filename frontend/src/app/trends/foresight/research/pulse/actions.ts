"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSameOriginHeaders } from "@/lib/apiGuards";
import { canReview } from "@/lib/review-access";
import { parsePulseWeek, pulsePath } from "@/lib/researchPulse";
import { startPulseWorker } from "@/lib/researchPulseWorker";

/**
 * "Recompute" for one Research Pulse theme (#73). A Server Action is a real
 * HTTP endpoint and this one starts GPU work on the workstation, so it has
 * the same two locks as the review queue: owner mode (canReview —
 * open on the owner instance, closed under PUBLIC_MODE and in the static
 * export, which does not even build /trends/foresight/*) and the
 * same-origin check from lib/apiGuards.ts.
 *
 * The weekly cron proposal (deploy/crontab.txt, not installed) and this
 * button write the same table; the page always shows the newest row.
 */
async function guard(): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  if (!isSameOriginHeaders(await headers())) throw new Error("cross-origin request refused");
}

export async function recomputePulseAction(formData: FormData): Promise<void> {
  await guard();
  const theme = String(formData.get("theme") ?? "").trim();
  const week = parsePulseWeek(String(formData.get("week") ?? ""));
  const r = startPulseWorker(theme, week);
  revalidatePath("/trends/foresight/research/pulse");
  const back = pulsePath(theme || undefined, week);
  redirect(`${back}${back.includes("?") ? "&" : "?"}worker=${r.ok ? "started" : r.reason}`);
}
