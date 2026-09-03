"use server";

import { revalidatePath } from "next/cache";
import { canReview } from "@/lib/review-access";
import {
  publishReviewed,
  rejectReviewed,
  requeueForRegeneration,
} from "@/lib/review";

/**
 * Review decisions (issue #71). Both re-check `canReview()` — a Server Action
 * is a real HTTP endpoint, so guarding only the page that renders the buttons
 * would leave the write path open.
 */

export async function publishAction(formData: FormData): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  await publishReviewed(id);
  revalidatePath("/trends/review");
}

export async function rejectAction(formData: FormData): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  await rejectReviewed(id);
  revalidatePath("/trends/review");
}

/**
 * Send a failed generation back to the pipeline instead of discarding it.
 * A refusal (attempts exhausted, no source entry) is reported rather than
 * thrown — the reviewer needs to know the article stayed put, and an unhandled
 * Server Action error would just show them a generic failure page.
 */
export async function requeueAction(formData: FormData): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  const result = await requeueForRegeneration(id);
  if (!result.ok && result.reason === "attempts_exhausted") {
    // Nothing left to try automatically; leave it for a manual decision.
    console.warn(`[review] regeneration attempts exhausted for trend ${id}`);
  }
  revalidatePath("/trends/review");
}
