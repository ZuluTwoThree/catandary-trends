import { redirect } from "next/navigation";
import { AUTH_ENABLED, getSession, isSafeInternalPath } from "@/lib/auth";
import SignInForm from "@/components/SignInForm";

export const dynamic = "force-dynamic";

export const metadata = { title: "Sign in — Catandary Trends" };

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!AUTH_ENABLED) redirect("/trends");
  const sp = await searchParams;
  const next = typeof sp.next === "string" && isSafeInternalPath(sp.next) ? sp.next : undefined;
  const session = await getSession();
  if (session) redirect(next ?? "/account");
  const error = typeof sp.error === "string" ? sp.error : undefined;
  const reason = typeof sp.reason === "string" ? sp.reason : undefined;
  return (
    <div className="mx-auto max-w-2xl px-6">
      <SignInForm error={error} next={next} reason={reason} />
    </div>
  );
}
