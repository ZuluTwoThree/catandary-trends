import type { Metadata } from "next";
import Link from "next/link";
import { Playfair_Display, JetBrains_Mono } from "next/font/google";
import { getTrends } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import "./radar.css";

const serif = Playfair_Display({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-radar-serif",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-radar-mono",
  display: "swap",
});

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Catandary Trend-Radar — Über 1.500 Signale pro Woche, kuratiert für Sie",
  description:
    "Wir sichten über 1.500 Trend-Signale pro Woche aus internationalen Primärquellen und kuratieren daraus Ihr individuelles Briefing. Täglich alarmiert, montags eingeordnet — auf Deutsch, auf Wunsch unter Ihrer Marke.",
};

const STRIPE_LINK_TEAM = process.env.NEXT_PUBLIC_STRIPE_LINK_TEAM || "";
const STRIPE_LINK_PRO = process.env.NEXT_PUBLIC_STRIPE_LINK_PRO || "";
const CONTACT_EMAIL = "radar@catandary.de";

const TRIAL_MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(
  "Trend-Radar 14-Tage-Test"
)}&body=${encodeURIComponent(
  `Guten Tag,

wir möchten das Trend-Radar 14 Tage kostenlos testen.

Unternehmen:
Ansprechpartner:
Relevante Branchen (Food / Tech / Health / Eco / Design / Fashion / Business / Lifestyle):
Watchlist-Themen (Wettbewerber, Technologien, Stichworte):

Mit freundlichen Grüßen`
)}`;

function streamTime(index: number): string {
  const minutes = 31 - index * 7;
  const h = minutes >= 0 ? 6 : 5;
  const m = ((minutes % 60) + 60) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function SignalItems() {
  const trends = getTrends({ status: "published", limit: 14 });
  const items = trends.map((t, i) => {
    const v = getVerticalInfo(t.primary_vertical);
    return (
      <Link href={`/trends/${t.slug}`} key={`${t.id}-${i}`} className="cr-signal">
        <div className="cr-sig-meta">
          <span className="cr-tag" style={{ color: v.color }}>
            {v.label.toUpperCase()}
          </span>
          <span className="cr-sig-time">{streamTime(i)}</span>
        </div>
        <div className="cr-sig-title">{t.title_de || t.title_en}</div>
        <div className="cr-sig-src">{t.source_name}</div>
      </Link>
    );
  });
  // duplicated set: seamless 50%-translateY loop
  return (
    <div className="cr-stream-track">
      {items}
      {trends.map((t, i) => {
        const v = getVerticalInfo(t.primary_vertical);
        return (
          <Link href={`/trends/${t.slug}`} key={`dup-${t.id}-${i}`} className="cr-signal" aria-hidden="true" tabIndex={-1}>
            <div className="cr-sig-meta">
              <span className="cr-tag" style={{ color: v.color }}>
                {v.label.toUpperCase()}
              </span>
              <span className="cr-sig-time">{streamTime(i)}</span>
            </div>
            <div className="cr-sig-title">{t.title_de || t.title_en}</div>
            <div className="cr-sig-src">{t.source_name}</div>
          </Link>
        );
      })}
    </div>
  );
}

function Tier({
  code,
  name,
  price,
  tagline,
  features,
  cta,
  ctaHref,
  highlight,
}: {
  code: string;
  name: string;
  price: string;
  tagline: string;
  features: string[];
  cta: string;
  ctaHref: string;
  highlight?: boolean;
}) {
  return (
    <div className={`cr-tier${highlight ? " highlight" : ""}`}>
      <div className="cr-tier-code">{code}</div>
      <h3 className="cr-serif cr-tier-name">{name}</h3>
      <div className="cr-price">
        <b>{price}</b>
        <span>€ / MONAT</span>
      </div>
      <p className="cr-tier-tagline">{tagline}</p>
      <ul className="cr-features">
        {features.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <a className={`cr-btn ${highlight ? "cr-btn-primary" : "cr-btn-ghost"}`} href={ctaHref}>
        {cta}
      </a>
    </div>
  );
}

export default function RadarLandingPage() {
  return (
    <div className={`cr-page ${serif.variable} ${mono.variable}`}>
      {/* ============ HERO ============ */}
      <header className="cr-hero">
        <div className="cr-wrap cr-hero-grid">
          <div className="cr-hero-main">
            <div className="cr-eyebrow cr-rise cr-d1">
              <span className="cr-dot" />
              CATANDARY TREND-RADAR&nbsp;·&nbsp;DACH
            </div>
            <h1 className="cr-serif cr-h1 cr-rise cr-d2">
              Über 1.500 Trend-Signale pro Woche. <em>Sie lesen nur die, die zählen.</em>
            </h1>
            <p className="cr-hero-sub cr-rise cr-d3">
              Niemand in Ihrem Team hat die Zeit, jede Woche 1.500 Artikel aus
              internationaler Fachpresse, Forschung und Presseverteilern zu screenen,
              zu bewerten und strategisch einzuordnen. Unser Radar tut genau das —
              und kuratiert daraus Ihr individuelles Briefing: täglich alarmiert,
              montags eingeordnet. Auf Deutsch, auf Wunsch unter Ihrer Marke.
            </p>
            <div className="cr-hero-ctas cr-rise cr-d4">
              <a className="cr-btn cr-btn-primary" href={TRIAL_MAILTO}>
                14 TAGE KOSTENLOS TESTEN
              </a>
              <a className="cr-btn cr-btn-ghost" href="#preise">
                PREISE ANSEHEN
              </a>
            </div>
            <div className="cr-metrics cr-rise cr-d5">
              <div className="cr-metric">
                <b>1.500+</b>
                <span>SIGNALE&nbsp;/&nbsp;WOCHE</span>
              </div>
              <div className="cr-metric">
                <b>128</b>
                <span>PRIMÄRQUELLEN</span>
              </div>
              <div className="cr-metric">
                <b>8</b>
                <span>BRANCHEN</span>
              </div>
              <div className="cr-metric">
                <b>Mo 06:30</b>
                <span>BRIEFING</span>
              </div>
            </div>
          </div>

          <aside className="cr-stream-col" aria-label="Live-Signal-Feed">
            <div className="cr-stream-head">
              <span className="cr-live">
                <span className="cr-dot" />
                SIGNAL-FEED
              </span>
              <span>LIVE · AUS DER PIPELINE</span>
            </div>
            <div className="cr-stream">
              <SignalItems />
            </div>
            <div className="cr-status">
              <span className="cr-live">
                <span className="cr-dot" />
              </span>
              <span>SYSTEM AKTIV</span>
              <span>OHNE TESTDATEN — ECHTE SIGNALE</span>
            </div>
          </aside>
        </div>
      </header>

      {/* ============ 01 WERT ============ */}
      <section className="cr-section">
        <div className="cr-wrap">
          <div className="cr-label">
            <b>01</b>WARUM EIN RADAR
          </div>
          <h2 className="cr-serif cr-h2">
            Die Sichtung ist die Arbeit. <em>Wir nehmen sie Ihnen ab.</em>
          </h2>
          <div className="cr-truths">
            <div className="cr-truth">
              <span className="cr-truth-n">I</span>
              <div>
                <h3>1.500+ Signale gesichtet — 20 gelesen</h3>
                <p>
                  Jede Woche werten wir über 1.500 Signale aus internationaler Fachpresse,
                  Forschungsmedien und Presseverteilern aus. Sie bekommen die relevantesten
                  für Ihre Branchen — <b>mit Relevanz-Score, PESTEL-Einordnung und Link zur
                  Originalquelle.</b> Das ersetzt ein bis zwei Beratertage Recherche pro Monat.
                </p>
              </div>
            </div>
            <div className="cr-truth">
              <span className="cr-truth-n">II</span>
              <div>
                <h3>Täglich alarmiert, montags eingeordnet</h3>
                <p>
                  Schlägt eines Ihrer Watchlist-Themen an — ein Wettbewerber, eine Technologie,
                  ein Begriff — erfahren Sie es <b>am nächsten Morgen per Alert</b>, nicht erst
                  im Wochenrückblick. Das Montags-Briefing liefert die kuratierte Synthese.
                </p>
              </div>
            </div>
            <div className="cr-truth">
              <span className="cr-truth-n">III</span>
              <div>
                <h3>White-Label für Ihr Geschäft</h3>
                <p>
                  Ab dem Pro-Tarif tragen Briefing und Portal Ihr Logo und Ihre Farben.
                  Beratungen versenden es als eigenes Produkt an ihre Mandanten — <b>aus
                  490 € Einkauf wird ein eigener Retainer-Baustein.</b>
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ 02 ABLAUF ============ */}
      <section className="cr-section">
        <div className="cr-wrap">
          <div className="cr-label">
            <b>02</b>SO FUNKTIONIERT ES
          </div>
          <h2 className="cr-serif cr-h2">
            Einmal kalibrieren. <em>Dann läuft es.</em>
          </h2>
          <div className="cr-steps">
            <div className="cr-step">
              <div className="cr-step-node" />
              <h3>BRANCHEN WÄHLEN</h3>
              <p>Aus 8 Vertikalen: Food, Tech, Health, Eco, Design, Fashion, Business, Lifestyle.</p>
            </div>
            <div className="cr-step">
              <div className="cr-step-node" />
              <h3>WATCHLIST DEFINIEREN</h3>
              <p>Bis zu 30 Begriffe: Wettbewerber, Technologien, Themen. Jederzeit per E-Mail änderbar.</p>
            </div>
            <div className="cr-step">
              <div className="cr-step-node" />
              <h3>ALERTS + BRIEFING</h3>
              <p>Tägliche Alerts bei Watchlist-Treffern, montags die kuratierte Wochen-Synthese — plus Portal mit allen Signalen.</p>
            </div>
            <div className="cr-step">
              <div className="cr-step-node" />
              <h3>WEITERVERWENDEN</h3>
              <p>Quellenlinks, PESTEL-Tags und Mega-Trend-Einordnung für Beratungs- und Pitch-Arbeit.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ 03 PREISE ============ */}
      <section className="cr-section" id="preise">
        <div className="cr-wrap">
          <div className="cr-label">
            <b>03</b>PREISE
          </div>
          <h2 className="cr-serif cr-h2">
            Drei Tarife. <em>Monatlich kündbar.</em>
          </h2>
          <div className="cr-tiers">
            <Tier
              code="RADAR / TEAM"
              name="Team"
              price="249"
              tagline="Das interne Trend-Radar für Ihr Team."
              features={[
                "3 Branchen Ihrer Wahl",
                "15 Watchlist-Begriffe",
                "Tägliche Watchlist-Alerts",
                "Wöchentliches Briefing (Deutsch)",
                "Mega-Trend-Monatsreport",
                "Bis 3 Empfänger",
              ]}
              cta={STRIPE_LINK_TEAM ? "JETZT ABONNIEREN" : "TEST STARTEN"}
              ctaHref={STRIPE_LINK_TEAM || TRIAL_MAILTO}
            />
            <Tier
              code="RADAR / PRO — MEISTGEWÄHLT"
              name="Pro"
              price="490"
              tagline="Für Beratungen und Agenturen mit Kundenkontakt."
              highlight
              features={[
                "Alle 8 Branchen",
                "30 Watchlist-Begriffe",
                "Tägliche Watchlist-Alerts",
                "White-Label: Ihr Logo, Ihre Farben",
                "Monats-Deep-Dive (PDF)",
                "Bis 5 Empfänger",
              ]}
              cta={STRIPE_LINK_PRO ? "JETZT ABONNIEREN" : "TEST STARTEN"}
              ctaHref={STRIPE_LINK_PRO || TRIAL_MAILTO}
            />
            <Tier
              code="RADAR / AGENCY"
              name="Agency"
              price="890"
              tagline="Für Beratungen, die Radare an Mandanten weitergeben."
              features={[
                "Alles aus Radar Pro",
                "3 getrennte Mandanten-Radare",
                "Eigenes Branding je Mandant",
                "Weitergabe- und Reseller-Recht",
                "Onboarding-Call inklusive",
              ]}
              cta="GESPRÄCH VEREINBAREN"
              ctaHref={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Trend-Radar Agency")}`}
            />
          </div>
          <p className="cr-price-note">
            Alle Preise zzgl. USt. · Jahreszahlung −15 % · Zum Vergleich: Ein Beratertag kostet
            1.200–1.800 €, ein Enterprise-Trendtool ab 10.000 € pro Jahr.
          </p>
        </div>
      </section>

      {/* ============ 04 FAQ ============ */}
      <section className="cr-section">
        <div className="cr-wrap">
          <div className="cr-label">
            <b>04</b>HÄUFIGE FRAGEN
          </div>
          <h2 className="cr-serif cr-h2">
            Was Sie vor dem Test <em>wissen wollen.</em>
          </h2>
          <div className="cr-faq">
            {[
              [
                "Woher kommen die Inhalte?",
                "Wir verarbeiten über 1.500 Signale pro Woche aus mehr als 100 verifizierten Primärquellen — internationale Fachpresse, Forschungsmedien, Presseverteiler und Marken-Newsrooms; das Quellennetz wächst laufend Richtung 300+. Jedes Signal verlinkt die Originalquelle. Keine Aggregator-Seiten, kein Scraping.",
              ],
              [
                "Wie unterscheidet sich das von WGSN oder Trendwatching?",
                "Diese Tools sind global, englischsprachig und kosten 8.000–30.000 € pro Jahr. Das Trend-Radar liefert auf Deutsch, fokussiert auf Ihre Branchen und Watchlist, und darf ab Pro-Tarif unter Ihrer Marke weiterverwendet werden — zu einem Bruchteil des Preises.",
              ],
              [
                "Was heißt White-Label genau?",
                "Briefing und Portal tragen Ihr Logo, Ihren Namen und Ihre Farbe. Im Agency-Tarif konfigurieren Sie bis zu drei getrennte Radare für Ihre Mandanten — jeweils mit eigenen Branchen, eigener Watchlist und eigenem Branding.",
              ],
              [
                "Wie schnell bin ich startklar?",
                "Nach Bestellung oder Test-Anfrage richten wir Ihr Radar am selben Werktag ein. Das erste Briefing kommt innerhalb von 24 Stunden, danach jeden Montag — Alerts ab dem ersten Treffer.",
              ],
              [
                "Kann ich monatlich kündigen?",
                "Ja. Keine Mindestlaufzeit, Kündigung per E-Mail genügt. Bei Jahreszahlung gilt der Rabatt von 15 %.",
              ],
            ].map(([q, a], i) => (
              <details key={q}>
                <summary>
                  <span className="cr-faq-n">{String(i + 1).padStart(2, "0")}</span>
                  <span className="cr-faq-q">{q}</span>
                  <span className="cr-faq-x">+</span>
                </summary>
                <div className="cr-faq-a">{a}</div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section className="cr-final">
        <div className="cr-wrap">
          <h2 className="cr-serif cr-h2" style={{ maxWidth: "none" }}>
            Zwei Briefings. Null Risiko. <em>Ihre Entscheidung.</em>
          </h2>
          <p>
            Starten Sie den 14-Tage-Test — Einrichtung am selben Werktag, ohne Kreditkarte.
            Sie bekommen zwei echte Briefings plus tägliche Alerts auf Ihre Themen.
          </p>
          <a className="cr-btn cr-btn-primary" href={TRIAL_MAILTO}>
            14 TAGE KOSTENLOS TESTEN
          </a>
          <div className="cr-final-foot">
            FRAGEN? <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL.toUpperCase()}</a>
            &nbsp;&nbsp;·&nbsp;&nbsp;
            <Link href="/trends">LIVE-BEISPIELE: CATANDARY TRENDS →</Link>
          </div>
        </div>
      </section>
    </div>
  );
}
