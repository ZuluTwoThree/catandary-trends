"use server";

import { revalidatePath } from "next/cache";
import { canReview } from "@/lib/review-access";
import { publishReviewed, rejectReviewed } from "@/lib/review";

/**
 * Review decisions (issue #71). Both re-check `canReview()` — a Server Action
 * is a real HTTP endpoint, so guarding only the page that renders the buttons
 * would leave the write path open.
 */

export async function publishAction(formData: FormData): Promise<void> {
  if (!(await canReview())) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  await publishReviewed(id);
  revalidatePath("/trends/review");
}

export async function rejectAction(formData: FormData): Promise<void> {
  if (!(await canReview())) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  await rejectReviewed(id);
  revalidatePath("/trends/review");
}
