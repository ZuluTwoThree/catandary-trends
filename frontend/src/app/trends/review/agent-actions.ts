"use server";

import { revalidatePath } from "next/cache";
import { canReview } from "@/lib/review-access";
import { proposalAt, readReportUncached } from "@/lib/agentReport";
import { applyBodyFix, dropSentencesWith, replaceName } from "@/lib/review";

/**
 * Apply one proposal the review agent made (issue: review effort, 2026-09-22).
 *
 * The browser posts the trend id and the INDEX of the proposal — never the text
 * to insert. The action re-reads the agent's report from disk and takes the
 * proposal from there, so a stale tab or a forged POST cannot write an arbitrary
 * string into an article. The repaired body then passes the same gates as
 * auto-publish; if one objects, nothing is written.
 */
export async function applyProposalAction(formData: FormData): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  const id = Number(formData.get("id"));
  const index = Number(formData.get("index"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  if (!Number.isInteger(index) || index < 0) throw new Error("bad index");

  const proposal = proposalAt(await readReportUncached(), id, index);
  if (!proposal) {
    console.warn(`[review] proposal ${index} for trend ${id} is gone — report changed?`);
    revalidatePath("/trends/review");
    return;
  }
  const transform =
    proposal.kind === "spelling" && proposal.to
      ? (body: string) => replaceName(body, proposal.what, proposal.to as string)
      : proposal.kind === "drop_sentence"
        ? (body: string) => dropSentencesWith(body, proposal.what)
        : null;
  if (!transform) throw new Error("unknown proposal kind");

  const result = await applyBodyFix(id, transform);
  if (!result.ok) {
    // The reviewer keeps the card and decides by hand — the article is untouched.
    console.warn(`[review] proposal ${proposal.kind} for trend ${id} refused: ${result.reason}`);
  }
  revalidatePath("/trends/review");
}
