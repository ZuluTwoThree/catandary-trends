"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSameOriginHeaders } from "@/lib/apiGuards";
import { canManageDossiers } from "@/lib/dossier-access";
import { startWorker, workerArgs, type StartResult } from "@/lib/dossierWorker";
import {
  approveDossierOrder,
  cancelDossierOrder,
  createDossierOrder,
  createRerunOrder,
  requeueDossierOrder,
} from "@/lib/dossiers";
import {
  approveAdvisoryNote,
  createAdvisoryNote,
  PROFILE_FIELDS,
  requeueAdvisoryNote,
  withdrawAdvisoryNote,
} from "@/lib/advisory";
import { startAdvisory } from "@/lib/advisoryWorker";

/**
 * Owner actions for the dossier desk (#95). Every action re-checks
 * canManageDossiers() — a Server Action is a real HTTP endpoint, so guarding
 * only the page that renders the buttons would leave the write path open
 * (same rule as the review queue actions) — and, because three of them start
 * GPU work on the workstation, the same-origin check from lib/apiGuards.ts
 * (Origin/Referer must name this host; Next's own action check is the first
 * lock, this is the second).
 *
 * Runs start ONLY from these buttons — the radar rule: a dossier is a dated
 * document recomputed on the owner's click, never on a cron.
 */

async function guard(): Promise<void> {
  if (!canManageDossiers()) throw new Error("not permitted");
  if (!isSameOriginHeaders(await headers())) throw new Error("cross-origin request refused");
}

function orderId(formData: FormData, field = "id"): number {
  const id = Number(formData.get(field));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  return id;
}

/** Desk notice for a start attempt: /trends/dossiers?worker=<code>. */
function noticeFor(r: StartResult): string {
  return r.ok ? "started" : r.reason;
}

export async function createOrderAction(formData: FormData): Promise<void> {
  await guard();
  const topic = String(formData.get("topic") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const question = String(formData.get("question") ?? "");
  const quant = formData.get("quant") === "on";
  const cpc = String(formData.get("cpc") ?? "");
  const id = await createDossierOrder({
    topic,
    cpc: cpc || undefined,
    slug: slug || undefined,
    question: question || undefined,
    quant,
  });
  revalidatePath("/trends/dossiers");
  if (id && formData.get("run") === "on") {
    const r = startWorker(workerArgs(id) ?? []);
    redirect(`/trends/dossiers?worker=${noticeFor(r)}&order=${id}`);
  }
}

export async function approveAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  await approveDossierOrder(id);
  revalidatePath("/trends/dossiers");
  const slug = String(formData.get("slug") ?? "");
  if (slug) revalidatePath(`/trends/dossiers/${slug}`);
}

export async function cancelAction(formData: FormData): Promise<void> {
  await guard();
  await cancelDossierOrder(orderId(formData));
  revalidatePath("/trends/dossiers");
}

export async function requeueAction(formData: FormData): Promise<void> {
  await guard();
  await requeueDossierOrder(orderId(formData));
  revalidatePath("/trends/dossiers");
}

/** Start the worker for exactly this order (a failed one is requeued by it). */
export async function runOrderAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  const r = startWorker(workerArgs(id) ?? []);
  revalidatePath("/trends/dossiers");
  redirect(`/trends/dossiers?worker=${noticeFor(r)}&order=${id}`);
}

/** Start the worker for every queued order (oldest first). */
export async function runQueuedAction(): Promise<void> {
  await guard();
  const r = startWorker([]);
  revalidatePath("/trends/dossiers");
  redirect(`/trends/dossiers?worker=${noticeFor(r)}`);
}

/** "Neu rechnen": next version of a series — new slip, worker started. */
export async function rerunSeriesAction(formData: FormData): Promise<void> {
  await guard();
  const slug = String(formData.get("slug") ?? "");
  const id = await createRerunOrder(slug);
  revalidatePath("/trends/dossiers");
  if (!id) redirect("/trends/dossiers?worker=noseries");
  const r = startWorker(workerArgs(id) ?? []);
  redirect(`/trends/dossiers?worker=${noticeFor(r)}&order=${id}`);
}

// --- Advisory notes (the Advisor, 2026-09-14) --------------------------------
// Options for ONE client from ONE dossier. Created here, run detached
// (scripts.advisory --note N, 27B with thinking), released ONLY by a person.

export async function createAdvisoryAction(formData: FormData): Promise<void> {
  await guard();
  const slug = String(formData.get("slug") ?? "");
  const version = Number(formData.get("version"));
  if (!slug || !Number.isInteger(version) || version <= 0) throw new Error("bad dossier");
  const profile: Record<string, string> = {};
  for (const [k] of PROFILE_FIELDS) profile[k] = String(formData.get(k) ?? "");
  const scope = String(formData.get("scope") ?? "");
  const id = await createAdvisoryNote({ dossierSlug: slug, dossierVersion: version, profile, scope });
  if (!id) throw new Error("note not created (scope missing?)");
  let notice = "created";
  if (formData.get("run") === "on") notice = noticeFor(startAdvisory(id));
  revalidatePath(`/trends/dossiers/${slug}`);
  redirect(`/trends/dossiers/${slug}/advisory/${id}?worker=${notice}`);
}

export async function runAdvisoryAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  const slug = String(formData.get("slug") ?? "");
  const r = startAdvisory(id);
  revalidatePath(`/trends/dossiers/${slug}/advisory/${id}`);
  redirect(`/trends/dossiers/${slug}/advisory/${id}?worker=${noticeFor(r)}`);
}

export async function requeueAdvisoryAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  const slug = String(formData.get("slug") ?? "");
  await requeueAdvisoryNote(id);
  const r = startAdvisory(id);
  revalidatePath(`/trends/dossiers/${slug}/advisory/${id}`);
  redirect(`/trends/dossiers/${slug}/advisory/${id}?worker=${noticeFor(r)}`);
}

export async function approveAdvisoryAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  const slug = String(formData.get("slug") ?? "");
  await approveAdvisoryNote(id, "owner", String(formData.get("note") ?? ""));
  revalidatePath(`/trends/dossiers/${slug}/advisory/${id}`);
  redirect(`/trends/dossiers/${slug}/advisory/${id}`);
}

export async function withdrawAdvisoryAction(formData: FormData): Promise<void> {
  await guard();
  const id = orderId(formData);
  const slug = String(formData.get("slug") ?? "");
  await withdrawAdvisoryNote(id);
  revalidatePath(`/trends/dossiers/${slug}/advisory/${id}`);
  redirect(`/trends/dossiers/${slug}/advisory/${id}`);
}
