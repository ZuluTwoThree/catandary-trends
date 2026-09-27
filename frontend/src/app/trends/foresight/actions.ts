"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSameOriginHeaders } from "@/lib/apiGuards";
import { canReview } from "@/lib/review-access";
import { startSnapshotWorker } from "@/lib/foresightSnapshotWorker";

/**
 * "Recompute" for the cluster layer (clusters + evolution pages). Same two
 * locks as the pulse recompute: owner mode (closed under PUBLIC_MODE and in
 * the static export, which never builds /trends/foresight/*) and same-origin.
 */
async function guard(): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  if (!isSameOriginHeaders(await headers())) throw new Error("cross-origin request refused");
}

export async function recomputeSnapshotAction(formData: FormData): Promise<void> {
  await guard();
  const mode = String(formData.get("mode") ?? "");
  const back = String(formData.get("back") ?? "");
  const r = startSnapshotWorker(mode);
  revalidatePath("/trends/foresight");
  revalidatePath("/trends/foresight/clusters");
  revalidatePath("/trends/foresight/evolution");
  revalidatePath("/trends/foresight/emerging");
  revalidatePath("/trends/foresight/map");
  const target = back.startsWith("/trends/foresight/") ? back : "/trends/foresight/clusters";
  redirect(`${target}${target.includes("?") ? "&" : "?"}worker=${r.ok ? "started" : r.reason}`);
}
