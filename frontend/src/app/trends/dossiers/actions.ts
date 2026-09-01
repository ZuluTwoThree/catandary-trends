"use server";

import { revalidatePath } from "next/cache";
import { canManageDossiers } from "@/lib/dossier-access";
import {
  approveDossierOrder,
  cancelDossierOrder,
  createDossierOrder,
  requeueDossierOrder,
} from "@/lib/dossiers";

/**
 * Owner actions for the dossier desk. Every action re-checks
 * canManageDossiers() — a Server Action is a real HTTP endpoint, so guarding
 * only the page that renders the buttons would leave the write path open
 * (same rule as the review queue actions).
 *
 * Placing an order only writes the slip — nothing starts running. The worker
 * is started by hand on the workstation (scripts/dossier_worker.py); there is
 * deliberately no "run now" endpoint and no cron (owner decision 2026-09-01).
 */

async function guard(): Promise<void> {
  if (!(await canManageDossiers())) throw new Error("not permitted");
}

export async function createOrderAction(formData: FormData): Promise<void> {
  await guard();
  const topic = String(formData.get("topic") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const question = String(formData.get("question") ?? "");
  const quant = formData.get("quant") === "on";
  await createDossierOrder({
    topic,
    slug: slug || undefined,
    question: question || undefined,
    quant,
  });
  revalidatePath("/trends/dossiers");
}

function orderId(formData: FormData): number {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("bad id");
  return id;
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
