import { q } from "@/lib/pg";
import { verifyUnsubscribe } from "@/lib/unsubscribe";

export const dynamic = "force-dynamic";

export const metadata = { title: "Unsubscribe — Catandary Trends" };

/**
 * One-click unsubscribe landing (GET, per RFC 8058 also reachable via the
 * List-Unsubscribe-Post header). Verifies the HMAC token, marks the subscriber
 * unsubscribed. Idempotent and safe to open twice.
 */
export default async function UnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const email = typeof sp.email === "string" ? sp.email : "";
  const token = typeof sp.token === "string" ? sp.token : "";
  const ok = verifyUnsubscribe(email, token);

  if (ok) {
    try {
      await q(
        "UPDATE newsletter_subscribers SET unsubscribed_at = NOW() " +
          "WHERE email = $1 AND unsubscribed_at IS NULL",
        [email.toLowerCase()]
      );
    } catch {
      // non-fatal — show success regardless (don't leak DB state)
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-20 text-center">
      {ok ? (
        <>
          <h1 className="text-2xl font-bold">You&apos;re unsubscribed</h1>
          <p className="mt-3 text-sm opacity-70">
            {email} will no longer receive the Catandary Trends newsletter. You can
            re-subscribe any time from the newsletter page.
          </p>
        </>
      ) : (
        <>
          <h1 className="text-2xl font-bold">Invalid unsubscribe link</h1>
          <p className="mt-3 text-sm opacity-70">
            This link is invalid or has expired. Manage your subscription from the
            newsletter page.
          </p>
        </>
      )}
      <a href="/trends/newsletter" className="mt-6 inline-block text-sm font-semibold underline">
        Back to the newsletter →
      </a>
    </div>
  );
}
