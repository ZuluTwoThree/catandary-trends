export const metadata = {
  title: "Privacy — Catandary Trends",
  description:
    "Privacy policy: what data Catandary Trends processes, why, and which EU processors are involved.",
};

/**
 * Privacy policy (GDPR Art. 13). Facts mirror the actual implementation:
 * session cookie for sign-in, email for magic links and the newsletter,
 * Stripe for billing, Resend for transactional email, Hetzner for hosting,
 * no third-party analytics and no tracking cookies. The controller block is
 * an owner gate before public launch (see imprint).
 */
const SECTIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Controller",
    body: (
      <>
        The controller for data processing on this site is the operator named in
        the{" "}
        <a href="/imprint" className="text-accent hover:underline">
          imprint
        </a>
        . Contact:{" "}
        <a href="mailto:trends@catandary.de" className="text-accent hover:underline">
          trends@catandary.de
        </a>
        .
      </>
    ),
  },
  {
    title: "What we process — and what we don't",
    body: (
      <>
        Browsing this site requires no account and no personal data. We use no
        third-party analytics and no tracking cookies. The trend-analysis
        pipeline behind the content runs on local models; reading the site does
        not send your data to AI providers.
      </>
    ),
  },
  {
    title: "Account & sign-in",
    body: (
      <>
        If you create an account, we store your email address and a session
        cookie so the sign-in works (legal basis: contract performance, Art.
        6(1)(b) GDPR). Sign-in links are sent via Resend (EU processing).
        Sessions expire automatically; you can sign out at any time.
      </>
    ),
  },
  {
    title: "Newsletter",
    body: (
      <>
        The weekly briefing is sent only after you actively subscribe. Every
        email contains an unsubscribe link; unsubscribing stops all further
        sends (legal basis: consent, Art. 6(1)(a) GDPR — revocable at any
        time).
      </>
    ),
  },
  {
    title: "Payments",
    body: (
      <>
        Paid plans are billed via Stripe. Stripe processes the payment data;
        we store only your subscription status and a Stripe customer
        reference, never card numbers (legal basis: contract performance,
        Art. 6(1)(b) GDPR).
      </>
    ),
  },
  {
    title: "Hosting",
    body: (
      <>
        This site is hosted on Hetzner infrastructure in the EU. Standard
        server logs (IP address, request time) are processed to operate and
        secure the service (legal basis: legitimate interest, Art. 6(1)(f)
        GDPR) and are not used for profiling.
      </>
    ),
  },
  {
    title: "Your rights",
    body: (
      <>
        You have the right to access, rectify and erase your data, to restrict
        processing, to data portability, and to object (Art. 15–21 GDPR), plus
        the right to lodge a complaint with a supervisory authority. Email{" "}
        <a href="mailto:trends@catandary.de" className="text-accent hover:underline">
          trends@catandary.de
        </a>{" "}
        to exercise any of these.
      </>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-14">
      <span className="eyebrow">Privacy</span>
      <h1 className="font-display text-[36px] leading-[1.1] text-paper mt-4 mb-8">
        Privacy policy
      </h1>
      {SECTIONS.map((s) => (
        <section key={s.title} className="mb-8">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-3">
            {s.title}
          </h2>
          <p className="text-[15px] leading-[1.7] text-foreground">{s.body}</p>
        </section>
      ))}
    </div>
  );
}
