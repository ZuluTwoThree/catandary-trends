import Link from "next/link";
import { verifyUnsubscribe } from "@/lib/unsubscribe";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Unsubscribe — Catandary Trends",
  description: "Manage your Catandary Trends briefing subscription.",
  robots: { index: false, follow: false },
};

const ACTION = "/api/newsletter/unsubscribe";

/**
 * Unsubscribe landing (security review 2026-09-02, E-7).
 *
 * GET only *shows* — it never writes. Link scanners in mail gateways and
 * preview panes open every URL in a message; the old page unsubscribed on
 * that first GET, so people were dropped without ever seeing the mail. Now
 * the page verifies the HMAC token (read-only) and offers a button; the
 * actual write happens in POST /api/newsletter/unsubscribe, which also
 * serves RFC 8058 one-click (src/proxy.ts rewrites provider POSTs on this
 * path to that route). Outcome states come back as ?done=1 / ?invalid=1 /
 * ?error=1.
 */
export default async function UnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const str = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : "");
  const email = str("email").trim();
  const token = str("token").trim();

  let view: "done" | "error" | "confirm" | "invalid";
  if (str("done") === "1") view = "done";
  else if (str("error") === "1") view = "error";
  else if (verifyUnsubscribe(email, token)) view = "confirm";
  else view = "invalid";

  return (
    <div className="mx-auto max-w-lg px-4 py-20 text-center">
      {view === "done" && (
        <>
          <h1 className="text-2xl font-bold">You&apos;re unsubscribed</h1>
          <p className="mt-3 text-sm opacity-70">
            This address will no longer receive the Catandary Trends newsletter. You
            can re-subscribe any time from the newsletter page.
          </p>
        </>
      )}
      {view === "error" && (
        <>
          <h1 className="text-2xl font-bold">Something went wrong</h1>
          <p className="mt-3 text-sm opacity-70">
            We could not process the unsubscribe right now. Please open the link
            from your mail again in a moment.
          </p>
        </>
      )}
      {view === "confirm" && (
        <>
          <h1 className="text-2xl font-bold">Unsubscribe from the briefing?</h1>
          <p className="mt-3 text-sm opacity-70">
            Confirm to stop the Catandary Trends newsletter for <strong>{email}</strong>.
          </p>
          <form method="post" action={ACTION} className="mt-6">
            <input type="hidden" name="email" value={email} />
            <input type="hidden" name="token" value={token} />
            <input type="hidden" name="confirm" value="1" />
            <button
              type="submit"
              className="inline-block border border-border px-5 py-2 text-sm font-semibold hover:bg-card/40"
            >
              Yes, unsubscribe me
            </button>
          </form>
        </>
      )}
      {view === "invalid" && (
        <>
          <h1 className="text-2xl font-bold">Invalid unsubscribe link</h1>
          <p className="mt-3 text-sm opacity-70">
            This link is invalid or has expired. Manage your subscription from the
            newsletter page.
          </p>
        </>
      )}
      <Link href="/trends/newsletter" className="mt-6 inline-block text-sm font-semibold underline">
        Back to the newsletter →
      </Link>
    </div>
  );
}
