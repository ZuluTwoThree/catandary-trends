/**
 * Privacy policy body + metadata, rendered by /privacy (workstation) and
 * /trends/privacy (static export) — see lib/sitePaths.ts.
 */
import { sitePath } from "@/lib/sitePaths";

export const PRIVACY_METADATA = {
  title: "Privacy — Catandary Trends",
  description:
    "Privacy policy: what data Catandary Trends processes, why, and which EU processors are involved.",
};

/**
 * Privacy policy (GDPR Art. 13). Facts mirror the actual implementation:
 * no accounts (no SaaS since #93 — sign-in and billing were removed
 * 2026-09-03), email only for the newsletter, Resend for its delivery,
 * Hetzner for hosting, no third-party analytics and no tracking cookies.
 * The controller block is an owner gate before public launch (see imprint).
 */
const SECTIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Controller",
    body: (
      <>
        The controller for data processing on this site is the operator named in
        the{" "}
        <a href={sitePath("/imprint")} className="text-accent hover:underline">
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
    title: "Newsletter",
    body: (
      <>
        The weekly briefing is sent only after you actively subscribe. Your
        address is stored for that purpose alone; delivery runs via Resend (EU
        processing). Every email contains an unsubscribe link;
        unsubscribing stops all further sends (legal basis: consent, Art.
        6(1)(a) GDPR — revocable at any time).
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

export default function PrivacyContent() {
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
