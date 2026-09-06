"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSameOriginHeaders } from "@/lib/apiGuards";
import { canReview } from "@/lib/review-access";
import { releaseEdition, withdrawRelease } from "@/lib/newsletterReview";

/**
 * Release decisions for the weekly briefing (owner mandate 2026-09-06).
 *
 * Both actions re-check canReview() — a Server Action is a real HTTP endpoint,
 * so guarding only the page that renders the buttons would leave the write
 * path open (same rule as the review queue) — plus the same-origin check from
 * lib/apiGuards.ts, because a release is what lets a mail go out to the list.
 *
 * Who released it: NEWSLETTER_APPROVER if set (the app has no accounts since
 * #93), otherwise "owner". It is an audit trail, not an authentication claim.
 */

async function guard(): Promise<void> {
  if (!canReview()) throw new Error("not permitted");
  if (!isSameOriginHeaders(await headers())) throw new Error("cross-origin request refused");
}

const MAX_NOTE = 500;

function editionKey(formData: FormData): { year: number; week: number } {
  const year = Number(formData.get("year"));
  const week = Number(formData.get("week"));
  if (!Number.isInteger(year) || year < 2020 || year > 2100) throw new Error("bad year");
  if (!Number.isInteger(week) || week < 1 || week > 53) throw new Error("bad week");
  return { year, week };
}

function back(year: number, week: number, notice: string): never {
  revalidatePath("/trends/newsletter/review");
  redirect(`/trends/newsletter/review?year=${year}&week=${week}&notice=${notice}`);
}

export async function releaseAction(formData: FormData): Promise<void> {
  await guard();
  const { year, week } = editionKey(formData);
  const note = String(formData.get("note") ?? "").trim().slice(0, MAX_NOTE);
  const by = process.env.NEWSLETTER_APPROVER || "owner";
  const ok = await releaseEdition(year, week, by, note || null);
  back(year, week, ok ? "released" : "release-failed");
}

export async function withdrawAction(formData: FormData): Promise<void> {
  await guard();
  const { year, week } = editionKey(formData);
  const ok = await withdrawRelease(year, week);
  back(year, week, ok ? "withdrawn" : "withdraw-failed");
}
