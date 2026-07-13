import { redirect } from "next/navigation";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import SignInForm from "@/components/SignInForm";

export const dynamic = "force-dynamic";

export const metadata = { title: "Sign in — Catandary Trends" };

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!AUTH_ENABLED) redirect("/trends");
  const session = await getSession();
  if (session) redirect("/account");
  const sp = await searchParams;
  const error = typeof sp.error === "string" ? sp.error : undefined;
  return (
    <div className="mx-auto max-w-2xl px-4">
      <SignInForm error={error} />
    </div>
  );
}
