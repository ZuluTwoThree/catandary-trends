import { redirect } from "next/navigation";

export default async function VerticalPage({
  params,
}: {
  params: Promise<{ v: string }>;
}) {
  const { v } = await params;
  redirect(`/trends?vertical=${v.toUpperCase()}`);
}
