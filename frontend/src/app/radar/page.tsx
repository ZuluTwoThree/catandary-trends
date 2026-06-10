import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Catandary Trend-Radar — Über 1.500 Signale pro Woche, kuratiert für Sie",
  description:
    "Wir sichten über 1.500 Trend-Signale pro Woche aus internationalen Primärquellen und kuratieren daraus Ihr individuelles Briefing. Täglich alarmiert, montags eingeordnet — auf Deutsch, auf Wunsch unter Ihrer Marke.",
};

const STRIPE_LINK_BASIC = process.env.NEXT_PUBLIC_STRIPE_LINK_BASIC || "";
const STRIPE_LINK_TEAM = process.env.NEXT_PUBLIC_STRIPE_LINK_TEAM || "";
const STRIPE_LINK_PRO = process.env.NEXT_PUBLIC_STRIPE_LINK_PRO || "";
const CONTACT_EMAIL = "radar@catandary.de";

const TRIAL_MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(
  "Trend-Radar 14-Tage-Test"
)}&body=${encodeURIComponent(
  `Hallo,

wir möchten das Trend-Radar 14 Tage kostenlos testen.

Unternehmen:
Ansprechpartner:
Interessante Branchen (Food / Tech / Health / Eco / Design / Fashion / Business / Lifestyle):
Themen für die Watchlist (Wettbewerber, Technologien, Stichworte):

Viele Grüße`
)}`;

function CheckIcon() {
  return (
    <svg
      className="w-4 h-4 flex-shrink-0 mt-0.5 text-emerald-400"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={3}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function TierCard({
  name,
  price,
  tagline,
  features,
  cta,
  ctaHref,
  highlighted,
}: {
  name: string;
  price: string;
  tagline: string;
  features: string[];
  cta: string;
  ctaHref: string;
  highlighted?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-7 flex flex-col ${
        highlighted
          ? "border-accent bg-accent/5 shadow-lg shadow-accent/10"
          : "border-border bg-card"
      }`}
    >
      {highlighted && (
        <span className="self-start text-xs font-bold uppercase tracking-wide text-accent mb-3 px-2 py-0.5 rounded-full border border-accent/40">
          Meistgewählt
        </span>
      )}
      <h3 className="text-xl font-bold">{name}</h3>
      <div className="mt-2 mb-1">
        <span className="text-4xl font-extrabold">{price}</span>
        <span className="text-muted text-sm"> € / Monat</span>
      </div>
      <p className="text-sm text-muted mb-5">{tagline}</p>
      <ul className="space-y-2.5 text-sm flex-grow">
        {features.map((f) => (
          <li key={f} className="flex gap-2">
            <CheckIcon />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      <a
        href={ctaHref}
        className={`mt-7 text-center font-semibold rounded-xl px-5 py-3 transition-colors ${
          highlighted
            ? "bg-accent text-white hover:opacity-90"
            : "border border-border hover:border-accent/50"
        }`}
      >
        {cta}
      </a>
    </div>
  );
}

export default function RadarLandingPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
      {/* Hero */}
      <section className="text-center max-w-3xl mx-auto">
        <p className="text-sm font-bold uppercase tracking-widest text-accent mb-4">
          Catandary Trend-Radar
        </p>
        <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight">
          Über 1.500 Trend-Signale pro Woche.
          <br />
          <span className="text-accent">Sie lesen nur die, die zählen.</span>
        </h1>
        <p className="mt-6 text-lg text-muted leading-relaxed">
          Niemand in Ihrem Team hat die Zeit, jede Woche 1.500 Artikel aus
          internationaler Fachpresse, Forschung und Presseverteilern zu
          screenen, zu bewerten und strategisch einzuordnen. Unser Radar tut
          genau das — und kuratiert daraus Ihr individuelles Briefing:
          personalisiert auf Ihre Branchen und Ihre Watchlist, täglich
          alarmiert, montags eingeordnet. Auf Deutsch, auf Wunsch unter
          Ihrer Marke.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <a
            href={TRIAL_MAILTO}
            className="bg-accent text-white font-semibold rounded-xl px-7 py-3.5 hover:opacity-90 transition-opacity"
          >
            14 Tage kostenlos testen
          </a>
          <Link
            href="/trends"
            className="border border-border font-semibold rounded-xl px-7 py-3.5 hover:border-accent/50 transition-colors"
          >
            Live-Beispiele ansehen
          </Link>
        </div>
        <p className="mt-3 text-xs text-muted">
          Ohne Kreditkarte. Zwei echte Briefings, dann entscheiden Sie.
        </p>
      </section>

      {/* Value props */}
      <section className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          {
            title: "1.500+ Signale gesichtet — 20 gelesen",
            body: "Jede Woche werten wir über 1.500 Signale aus internationaler Fachpresse, Forschungsmedien und Presseverteilern aus. Sie bekommen die relevantesten für Ihre Branchen — mit Relevanz-Score, PESTEL-Einordnung und Link zur Originalquelle. Das ersetzt 1–2 Beratertage Recherche pro Monat.",
          },
          {
            title: "Täglich alarmiert, montags eingeordnet",
            body: "Schlägt eines Ihrer Watchlist-Themen an — ein Wettbewerber, eine Technologie, ein Begriff — erfahren Sie es am nächsten Morgen per Alert, nicht erst im Wochenrückblick. Das Montags-Briefing liefert dann die kuratierte Synthese der Woche.",
          },
          {
            title: "White-Label für Ihr Geschäft",
            body: "Ab dem Pro-Tarif tragen Briefing und Portal Ihr Logo und Ihre Farben. Beratungen versenden es als eigenes Produkt an ihre Mandanten — aus 490 € Einkauf wird ein eigener Retainer-Baustein.",
          },
        ].map((v) => (
          <div key={v.title} className="rounded-2xl border border-border bg-card p-6">
            <h3 className="font-bold text-lg mb-2">{v.title}</h3>
            <p className="text-sm text-muted leading-relaxed">{v.body}</p>
          </div>
        ))}
      </section>

      {/* How it works */}
      <section className="mt-20">
        <h2 className="text-2xl font-bold text-center mb-10">
          So funktioniert es
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 text-center">
          {[
            ["1", "Branchen wählen", "Aus 8 Vertikalen: Food, Tech, Health, Eco, Design, Fashion, Business, Lifestyle."],
            ["2", "Watchlist definieren", "Bis zu 30 Begriffe: Wettbewerber, Technologien, Themen."],
            ["3", "Alerts + Briefing erhalten", "Tägliche Alerts bei Watchlist-Treffern, montags die kuratierte Wochen-Synthese — plus Portal mit allen Signalen."],
            ["4", "Weiterverwenden", "Quellenlinks, PESTEL-Tags und Mega-Trend-Einordnung für Ihre Beratungs- und Pitch-Arbeit."],
          ].map(([num, title, body]) => (
            <div key={num}>
              <div className="w-10 h-10 mx-auto rounded-full bg-accent/15 text-accent font-bold flex items-center justify-center mb-3">
                {num}
              </div>
              <h3 className="font-semibold mb-1">{title}</h3>
              <p className="text-sm text-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="mt-20" id="preise">
        <h2 className="text-2xl font-bold text-center mb-2">Preise</h2>
        <p className="text-center text-muted mb-10">
          Monatlich kündbar. Jahreszahlung: 15 % Rabatt.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          <TierCard
            name="Radar Basic"
            price="99"
            tagline="Der Einstieg: eine Branche im Blick behalten."
            features={[
              "1 Branche Ihrer Wahl",
              "5 Watchlist-Begriffe",
              "Wöchentliches Briefing (Deutsch)",
              "Radar-Portal mit allen Signalen",
              "1 Empfänger",
            ]}
            cta={STRIPE_LINK_BASIC ? "Jetzt abonnieren" : "Test starten"}
            ctaHref={STRIPE_LINK_BASIC || TRIAL_MAILTO}
          />
          <TierCard
            name="Radar Team"
            price="249"
            tagline="Das interne Trend-Radar für Ihr Team."
            features={[
              "3 Branchen Ihrer Wahl",
              "15 Watchlist-Begriffe",
              "Tägliche Watchlist-Alerts",
              "Mega-Trend-Monatsreport",
              "Bis 3 Empfänger",
            ]}
            cta={STRIPE_LINK_TEAM ? "Jetzt abonnieren" : "Test starten"}
            ctaHref={STRIPE_LINK_TEAM || TRIAL_MAILTO}
          />
          <TierCard
            name="Radar Pro"
            price="490"
            tagline="Für Beratungen und Agenturen mit Kundenkontakt."
            highlighted
            features={[
              "Alle 8 Branchen",
              "30 Watchlist-Begriffe",
              "Tägliche Watchlist-Alerts",
              "White-Label: Ihr Logo, Ihre Farben",
              "Monats-Deep-Dive (PDF)",
              "Bis 5 Empfänger",
            ]}
            cta={STRIPE_LINK_PRO ? "Jetzt abonnieren" : "Test starten"}
            ctaHref={STRIPE_LINK_PRO || TRIAL_MAILTO}
          />
          <TierCard
            name="Radar Agency"
            price="890"
            tagline="Für Beratungen, die Radare an Mandanten weitergeben."
            features={[
              "Alles aus Radar Pro",
              "3 getrennte Mandanten-Radare",
              "Eigenes Branding je Mandant",
              "Weitergabe- und Reseller-Recht",
              "Onboarding-Call inklusive",
            ]}
            cta="Gespräch vereinbaren"
            ctaHref={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(
              "Trend-Radar Agency"
            )}`}
          />
        </div>
        <p className="text-center text-sm text-muted mt-6">
          Zum Vergleich: Ein einzelner Beratertag kostet 1.200–1.800 €, ein
          Enterprise-Trendtool ab 10.000 € pro Jahr.
        </p>
      </section>

      {/* FAQ */}
      <section className="mt-20 max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-8">
          Häufige Fragen
        </h2>
        <div className="space-y-4">
          {[
            [
              "Woher kommen die Inhalte?",
              "Wir verarbeiten über 1.500 Signale pro Woche aus mehr als 100 verifizierten Primärquellen — internationale Fachpresse, Forschungsmedien, Presseverteiler und Marken-Newsrooms; das Quellennetz wächst laufend Richtung 300+. Jedes Signal verlinkt die Originalquelle. Keine Aggregator-Seiten, kein Scraping.",
            ],
            [
              "Wie unterscheidet sich das von WGSN oder Trendwatching?",
              "Diese Tools sind global, englischsprachig und kosten 8.000–30.000 € pro Jahr. Das Trend-Radar liefert auf Deutsch, fokussiert auf Ihre Branchen und Watchlist, und darf ab Pro-Tier unter Ihrer Marke weiterverwendet werden — zu einem Bruchteil des Preises.",
            ],
            [
              "Was heißt White-Label genau?",
              "Briefing und Portal tragen Ihr Logo, Ihren Namen und Ihre Farbe. Im Agency-Tier konfigurieren Sie bis zu drei getrennte Radare für Ihre Mandanten — jeweils mit eigenen Branchen, eigener Watchlist und eigenem Branding.",
            ],
            [
              "Wie schnell bin ich startklar?",
              "Nach Bestellung oder Test-Anfrage richten wir Ihr Radar am selben Werktag ein. Das erste Briefing kommt innerhalb von 24 Stunden, danach jeden Montag.",
            ],
            [
              "Kann ich monatlich kündigen?",
              "Ja. Keine Mindestlaufzeit, Kündigung per E-Mail genügt. Bei Jahreszahlung gilt der Rabatt von 15 %.",
            ],
          ].map(([q, a]) => (
            <details
              key={q}
              className="rounded-xl border border-border bg-card p-5 group"
            >
              <summary className="font-semibold cursor-pointer list-none flex justify-between items-center">
                {q}
                <span className="text-muted group-open:rotate-45 transition-transform text-xl leading-none">
                  +
                </span>
              </summary>
              <p className="text-sm text-muted leading-relaxed mt-3">{a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="mt-20 text-center rounded-2xl border border-accent/30 bg-accent/5 p-10">
        <h2 className="text-2xl font-bold">
          Zwei Briefings. Null Risiko. Ihre Entscheidung.
        </h2>
        <p className="text-muted mt-2 mb-6">
          Starten Sie den 14-Tage-Test — Einrichtung am selben Werktag, ohne
          Kreditkarte.
        </p>
        <a
          href={TRIAL_MAILTO}
          className="inline-block bg-accent text-white font-semibold rounded-xl px-8 py-4 hover:opacity-90 transition-opacity"
        >
          14 Tage kostenlos testen
        </a>
        <p className="mt-4 text-xs text-muted">
          Fragen? <a href={`mailto:${CONTACT_EMAIL}`} className="underline">{CONTACT_EMAIL}</a>
        </p>
      </section>
    </div>
  );
}
